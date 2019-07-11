# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import difflib
import cgi
import pytz
import time

from urllib.parse import urlparse
from email.mime.text import MIMEText
from email.header import Header
from collections import OrderedDict

from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.sendmail import sendmail_transactional
from trytond.config import config
from trytond.transaction import Transaction

__all__ = ['WorkParty', 'Work']

FROM_ADDR = config.get('email', 'from')
URL = config.get('project_contact', 'url')

class WorkParty(ModelSQL):
    'Work Party'
    __name__ = "project.work-party.party"

    work = fields.Many2One('project.work', 'Work',
        required=True, select=True, ondelete='CASCADE')
    party = fields.Many2One('party.party', 'Party', required=True, select=True)


class Work(metaclass=PoolMeta):
    __name__ = "project.work"

    allowed_contacts = fields.Function(fields.Many2Many('party.party',
            None, None, 'Allowed Contacts'),
        'on_change_with_allowed_contacts')
    contacts = fields.Many2Many('project.work-party.party', 'work',
        'party', 'Contacts',
        domain=[
            ('id', 'in', Eval('allowed_contacts', [])),
            ],
        depends=['allowed_contacts'])

    @classmethod
    def __setup__(cls):
        super(Work,cls).__setup__()
        cls._buttons.update({
                'send_summary': {},
                })

    @staticmethod
    def default_contacts():
        DefaultRule = Pool().get('project.work.default_rule')
        pattern = {
            'project': None,
            }
        contacts = DefaultRule.compute(pattern)
        return [x.id for x in contacts]

    @fields.depends('parent',  methods=['get_default_rule_pattern'])
    def on_change_with_contacts(self, name=None):
        DefaultRule = Pool().get('project.work.default_rule')
        pattern = self.get_default_rule_pattern()
        contacts = DefaultRule.compute(pattern)
        # Removes the list of existing contacts
        return [x.id for x in contacts]

    def get_default_rule_pattern(self):
        return {
            'project': self.parent.id if self.parent else None,
            }

    @fields.depends('party', 'company')
    def on_change_with_allowed_contacts(self, name=None):
        pool = Pool()
        Employee = pool.get('company.employee')
        res = [e.party.id for e in Employee.search([])]
        if not self.party:
            return res
        res.extend(r.to.id for r in self.party.relations)
        return res

    @staticmethod
    def get_mail_fields():
        # Dictionary for One2Many values
        fields = ['name', 'effort_duration', 'comment', 'state']
        res = OrderedDict.fromkeys(fields)
        return res

    def get_mail(self, one2many_values=None, old_values=None):
        pool = Pool()
        Employee = pool.get('company.employee')

        if old_values is None:
            old_values = {}
            for field in self.get_mail_fields():
                old_values.fromkeys(field, None)
        if one2many_values is None:
            one2many_values = {}

        def get_value(field, value):
            if isinstance(getattr(self.__class__, field), fields.Many2One):
                if value:
                    if isinstance(value, int):
                        Model = Pool().get(getattr(self.__class__,
                                field).model_name)
                        value = Model(value)
                    return value.rec_name
            return value

        to_addr = []
        employees = [e.party.id for e in Employee.search([])]

        uid = self.write_uid or self.create_uid
        if uid:
            discard_employees = [ce.party.id for ce in uid.employees
                if not uid.send_own_changes]
            employees = set(employees) - set(discard_employees)

        for party in self.contacts:
            if party.id in employees:
                to_addr.append(party.email)

        url = '%s/model/project.work/%s' % (URL, getattr(self,'id'))
        name = self.rec_name

        body = []
        body.append(u'<div style="background: #EEEEEE; padding-left: 10px; '
                'padding-bottom: 10px">'
                '<a href="%(url)s">'
                '<h2 style="margin: 0px 0px 0px 0px; '
                'padding: 0px 0px 0px 0px;">%(name)s</h2>'
                '</a>' % {
                'url':url,
                'name' : name,
                })

        for field, subfields in self.get_mail_fields().items():
            if old_values.get(field) == getattr(self, field):
                continue
            diff=[]
            if isinstance(getattr(self.__class__, field), fields.Text):
                old = old_values.get(field) or ''
                old = old.splitlines(1)
                new = getattr(self, field) or ''
                new = new.splitlines(1)
                diffs = difflib.unified_diff(old, new, n=3)
                title = ' '.join([x.capitalize() for x in field.split('_')])
                body.append(u'<br><b>{}</b>:'.format(title))
                for diff in diffs:
                    diff = cgi.escape(diff)
                    if (diff.startswith('@') or diff.startswith('+++')
                            or diff.startswith('---')):
                        continue
                    if (diff.startswith('-')):
                        body.append(u'<font color="red">%s</font>' %
                            diff.rstrip('\n'))
                        continue
                    if (diff.startswith('+')):
                        body.append(u'<font color="green">%s</font>' %
                            diff.rstrip('\n'))
                        continue
                    else:
                        body.append(diff.rstrip('\n'))
                        continue
            elif isinstance(getattr(self.__class__, field), fields.One2Many):
                related_model = Pool().get(getattr(self.__class__,
                            field).model_name)
                for one2many in one2many_values.get(field, []):
                    for subfield in subfields:
                        if isinstance(getattr(related_model, subfield),
                                fields.Text):
                            texts = one2many.get(subfield) or ''
                            texts = texts.splitlines(1)
                            title = ' '.join([x.capitalize() for x in subfield.split('_')])
                            body.append(u'<b>{}</b>:'.format(title))
                            for text in texts:
                                text = cgi.escape(text)
                                body.append(text)
                        elif isinstance(getattr(related_model, subfield),
                                fields.DateTime):
                            date = one2many.get(subfield)
                            date = date.strftime('%Y-%m-%d %H:%M') if date else '/'
                            title = ' '.join([x.capitalize() for x in subfield.split('_')])
                            body.append(u'<b>{}</b>: {}'.format(title,date))
                        elif isinstance(getattr(related_model, subfield),
                                fields.Many2One):
                            Model = Pool().get(getattr(related_model,
                                    subfield).model_name)
                            value = Model(one2many.get(subfield))
                            title = ' '.join([x.capitalize() for x in subfield.split('_')])
                            body.append(u'<b>{}</b>: {}'.format(title,value.rec_name))
                        else:
                            title = ' '.join([x.capitalize() for x in subfield.split('_')])
                            body.append(u'<b>{}</b>: {}'.format(title,one2many.get(subfield)))
                    body.append(u'<br><hr style="border-top: 1px dashed;">')
            else:
                title = ' '.join([x.capitalize() for x in field.split('_')])
                body.append(u'<b>{}</b>:'.format(title))
                if field in old_values:
                    body.append(u'<font color="red">- {} </font>'.format(
                        get_value(field, old_values[field])))
                body.append(u'<font color="green"> + {} </font>'.format(
                    get_value(field, getattr(self, field))))

        Company = pool.get('company.company')
        company_id = Transaction().context.get('company')
        date = self.write_date or self.create_date
        if company_id:
            company = Company(company_id)
            if company.timezone:
                timezone = pytz.timezone(company.timezone)
                date = timezone.localize(date)
                date = date + date.utcoffset()

        date = date.strftime('%Y-%m-%d %H:%M') if date else '/'
        body.append('<br>'
                    '<small>'
                    '%(operation)s by %(write_user)s on %(write_date)s'
                    '</small>' % {
                    'operation': 'Updated' if old_values else 'Created',
                    'write_user': uid.name,
                    'write_date' : date,
                    })

        body.append(u'</div>')
        body = u'<br/>\n'.join(body)
        body = u'''<html><head>
            <meta http-equiv="Content-Type" content="text/html;charset=utf-8">
            </head>
            <body style="font-family: courier">%s</body>
            </html>''' % body

        msg = MIMEText(body, 'html',_charset='utf-8')
        msg['From'] = FROM_ADDR
        msg['To'] = ', '.join(to_addr)
        msg['Subject'] = Header(u"Changes in %s" % self.rec_name, 'utf-8')

        url = urlparse(url)
        if old_values:
            msg['In-Reply-To'] = "<{}@{}>".format(self.id, url.netloc)
        return msg

    @classmethod
    def create(cls, vlist):
        records = super(Work, cls).create(vlist)
        for record in records:
            for values in vlist:
                record.send_mail(record.get_mail())
        return records

    @classmethod
    def write(cls, *args):
        SummaryContacts = Pool().get('project.work.summary_contacts')

        to_addr = []
        ready_to_send_summary = []
        to_send = []
        actions = iter(args)

        for records, values in zip(actions, actions):
            if values.get('state') == 'done':
                ready_to_send_summary += records

            if not (set(values.keys()) & set(cls.get_mail_fields())):
                continue

            for record in records:
                old_values = {}
                o2mv = {}
                for field in cls.get_mail_fields():
                    old_values[field] = getattr(record, field)

                    if isinstance(getattr(record.__class__, field),
                        fields.One2Many):

                        if not field in values:
                            continue
                        if values[field][0][0] != 'create':
                            continue

                        for one2many_list in values[field][0][1]:
                            o2mv.setdefault(field, []).append(one2many_list)
                to_send.append((record, old_values, o2mv))

            for work in records:
                for party in work.contacts:
                    to_addr.append(party.email)

        super(Work, cls).write(*args)

        for record, old_values, one2many_values in to_send:
            record.send_mail(record.get_mail(one2many_values,
                    old_values))

        for work in ready_to_send_summary:
            to_addr.extend(SummaryContacts.get_mail())
            pattern = work.get_summary_contacts_pattern()
            to_addr = SummaryContacts.compute(pattern)
            work.send_summary_mail(to_addr)

    def get_summary_contacts_pattern(self):
        return {
            'project': self.parent.id if self.parent else None,
            }

    def get_summary_mail(self, to_addr):
        Employee = Pool().get('company.employee')
        Company = Pool().get('company.company')

        to_addr = []
        employees = [e.party.id for e in Employee.search([])]

        uid = self.write_uid or self.create_uid
        if uid:
            discard_employees = [ce.party.id for ce in uid.employees
                if not uid.send_own_changes]
            employees = set(employees) - set(discard_employees)

        for party in self.contacts:
            if party.id in employees:
                to_addr.append(party.email)

        def get_value(field, value):
            if isinstance(getattr(self.__class__, field), fields.Many2One):
                if value:
                    if isinstance(value, int):
                        Model = Pool().get(getattr(self.__class__,
                                field).model_name)
                        value = Model(value)
                    return value.rec_name
            return value

        url = '%s/model/project.work/%s' % (URL, getattr(self,'id'))
        name = self.rec_name

        body = []

        body.append(u'<div style="background: #EEEEEE; padding-left: 10px; '
                'padding-bottom: 10px">'
                '<a href="%(url)s">'
                '<h2 style="margin: 0px 0px 0px 0px; '
                'padding: 0px 0px 0px 0px;"> %(name)s </h2>'
                '</a>'
                % {
                'url':url,
                'name' : name,
                })

        for field in self.get_mail_fields():
            if isinstance(getattr(self.__class__, field), fields.One2Many):
                continue
            elif isinstance(getattr(self.__class__, field), fields.Text):
                texts = getattr(self, field) or ''
                texts = texts.splitlines(1)
                title = ' '.join([x.capitalize() for x in field.split('_')])
                body.append(u'<b>{}</b>:'.format(title))
                for text in texts:
                    text = cgi.escape(text)
                    body.append(text)
            else:
                title = ' '.join([x.capitalize() for x in field.split('_')])
                body.append(u'<b>{}</b>: {}'.format(title,get_value(field,
                            getattr(self, field))))


        company_id = Transaction().context.get('company')
        date = self.write_date or self.create_date
        if company_id:
            company = Company(company_id)
            if company.timezone:
                timezone = pytz.timezone(company.timezone)
                date = timezone.localize(date)
                date = date + date.utcoffset()

        date = date.strftime('%Y-%m-%d %H:%M') if date else '/'
        body.append('<br>'
                    '<small>'
                    'Closed by %(write_user)s on %(write_date)s'
                    '</small>' % {
                    'write_user': uid.name,
                    'write_date' : date,
                    })

        body.append(u'</div>')
        body = u'<br/>\n'.join(body)
        body = u'''<html><head>
            <meta http-equiv="Content-Type" content="text/html;charset=utf-8">
            </head>
            <body style="font-family: courier">%s</body>
            </html>''' % body

        msg = MIMEText(body, 'html',_charset='utf-8')
        msg['From'] = FROM_ADDR
        msg['To'] = ', '.join(to_addr)
        msg['Subject'] = Header(u'Summary of %s' % self.rec_name, 'utf-8')

        url = urlparse(url)
        msg['In-Reply-To'] = "<{}@{}>".format(self.id, url.netloc)
        return msg

    def send_summary_mail(self, to_addr):
        msg = self.get_summary_mail(to_addr)
        sendmail_transactional(msg['From'],msg['To'],msg)

    def send_mail(self, msg):
        sendmail_transactional(msg['From'],msg['To'],msg)

    @classmethod
    @ModelView.button
    def send_summary(cls, works):
        SummaryContacts = Pool().get('project.work.summary_contacts')
        to_addr = []
        to_addr.extend(SummaryContacts.get_mail())
        for work in works:
            work.send_summary_mail(to_addr)

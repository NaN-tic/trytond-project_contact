# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import difflib
from email.mime.text import MIMEText
from email.header import Header
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.sendmail import sendmail
from trytond.config import config

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

    @fields.depends('parent')
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
        return ['name', 'effort_duration', 'comment', 'state']

    def get_mail(self, old_values=None):
        pool = Pool()
        Employee = pool.get('company.employee')

        if old_values is None:
            old_values = {}
            for field in self.get_mail_fields():
                old_values.fromkeys(field, None)

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
        res = [e.party.id for e in Employee.search([])]

        for party in self.contacts:
            if party.id in res:
                to_addr.append(party.email)

        url = '%s/model/project.work/%s' % (URL, getattr(self,'id'))
        name = self.rec_name

        body = []
        body.append(u'<div style="background: #EEEEEE; padding-left: 10px; '
            'padding-bottom: 10px">'
            '<h2> %s </h2>' % name)

        for field in self.get_mail_fields():
            if old_values.get(field) == getattr(self, field):
                continue

            diff=[]
            if isinstance(getattr(self.__class__, field), fields.Text):
                old = old_values.get(field) or ''
                old = old.splitlines(1)
                new = getattr(self, field) or ''
                new = new.splitlines(1)
                diffs = difflib.unified_diff(old, new, n=3)
                body.append(u'<br><b>{}</b>:'.format(field))
                for diff in diffs:
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

            else:
                body.append(u'<br><b>{}</b>:'.format(field))
                if field in old_values:
                    body.append( u'<font color="red">- {} </font>'.format(
                        get_value(field, old_values[field])))
                body.append(u'<font color="green"> + {} </font>'.format(
                    get_value(field, getattr(self, field))))

        body.append(u'<br><small>'
            '<a href="%(url)s">%(id)s</a>'
            '</small>' % {
                'url': url,
                'id' : self.rec_name,
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

        actions = iter(args)
        args  = []

        old_values = {}
        to_addr = []
        ready_to_send_summary = []
        check_in_email_fields = []
        for records, values in zip(actions, actions):
            if values.get('state') == 'done':
                ready_to_send_summary += records

            if set(values.keys()) & set(cls.get_mail_fields()):
                check_in_email_fields += records

            for record in records:
                old_values[record.id] = {}
                for field in cls.get_mail_fields():
                    old_values[record.id][field] = getattr(record, field)

            for work in records:
                for party in work.contacts:
                    to_addr.append(party.email)
            args.extend((records, values))

        super(Work, cls).write(*args)

        actions = iter(args)
        for record in check_in_email_fields:
            record.send_mail(record.get_mail(old_values[record.id]))

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
        res = [e.party.id for e in Employee.search([])]

        for party in self.contacts:
            if party.id in res:
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
            '<h2>%s</h2>' %name)

        for field in self.get_mail_fields():
            if isinstance(getattr(self.__class__, field), fields.Text):
                texts = getattr(self, field) or ''
                texts = texts.splitlines(1)
                body.append(u'<br><b>{}</b>:'.format(field))
                for text in texts:
                    body.append(text)
            else:
                body.append(u'<br><b>{}</b>:'.format(field))
                body.append(u'<font> {} </font>'.format(get_value(field,
                           getattr(self, field))))

        body.append(u'<br><small>'
            '<a href="%(url)s">%(id)s</a>'
            '</small>' % {
                'url': url,
                'id' : self.rec_name,
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
        return msg

    def send_summary_mail(self, to_addr):
        msg = self.get_summary_mail(to_addr)
        sendmail(msg['From'],msg['To'],msg)

    def send_mail(self, msg):
        sendmail(msg['From'],msg['To'],msg)

    @classmethod
    @ModelView.button
    def send_summary(cls, works):
        SummaryContacts = Pool().get('project.work.summary_contacts')
        to_addr = []
        to_addr.extend(SummaryContacts.get_mail())
        for work in works:
            work.send_summary_mail(to_addr)

from trytond.model import (ModelSQL, ModelView, MatchMixin, fields)

__all__ = ['SummaryContacts']


class SummaryContacts(MatchMixin, ModelSQL, ModelView):
    'Summary Contacts'
    __name__ = 'project.work.summary_contacts'

    project = fields.Many2One('project.work', 'Project')
    contacts = fields.Many2One('party.party', 'Contacts')

    @classmethod
    def get_mail(cls):
        emails = []
        for contact in cls.search([]):
            emails.append(contact.contacts.email)
        return emails

    @classmethod
    def compute(cls, pattern):
        emails = []
        for contact in cls.search([]):
            if contact.match(pattern):
                emails.append(contact.contacts.email)
        return emails

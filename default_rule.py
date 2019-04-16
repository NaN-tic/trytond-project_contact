from trytond.model import (ModelSQL, ModelView, MatchMixin, fields,
    sequence_ordered)

__all__ = ['DefaultRule', 'ContactParty']


class ContactParty(ModelSQL):
    'Contact Party'
    __name__ = 'project.work.default_rule-party.party'

    rule = fields.Many2One('project.work.default_rule', 'Rule',
        required=True, select=True, ondelete='CASCADE')
    party = fields.Many2One('party.party', 'Party', required=True, select=True,
        ondelete='CASCADE')


class DefaultRule(sequence_ordered(), MatchMixin, ModelSQL, ModelView):
    'Default Rule'
    __name__ = 'project.work.default_rule'

    project = fields.Many2One('project.work', 'Project')
    contacts = fields.Many2Many('project.work.default_rule-party.party', 'rule',
             'party','Contacts')


    @classmethod
    def compute(cls, pattern):
        contacts = []
        for rule in cls.search([]):
            if rule.match(pattern):
                contacts += rule.contacts
        return contacts

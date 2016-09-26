# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval

__all__ = ['WorkParty', 'Work']
__metaclass__ = PoolMeta


class WorkParty(ModelSQL):
    'Work'
    __name__ = "project.work-party.party"

    work = fields.Many2One('project.work', 'Work',
        required=True, select=True, ondelete='CASCADE')
    party = fields.Many2One('party.party', 'Party', required=True, select=True)


class Work:
    'Work'
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

    @fields.depends('party', methods=['party'])
    def on_change_with_allowed_contacts(self, name=None):
        pool = Pool()
        Employee = pool.get('company.employee')
        res = [e.party.id for e in Employee.search([])]
        self.on_change_with_party()
        if not self.party:
            return res
        res.extend(r.to.id for r in self.party.relations)
        return res

# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import work
from . import default_rule
from . import summary_contacts
from . import user

def register():
    Pool.register(
        work.WorkParty,
        work.Work,
        default_rule.ContactParty,
        default_rule.DefaultRule,
        summary_contacts.SummaryContacts,
        user.User,
        module='project_contact', type_='model')

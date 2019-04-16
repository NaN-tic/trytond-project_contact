from trytond.pool import PoolMeta
from trytond.model import fields

__all__ = ['User']


class User(metaclass=PoolMeta):
    __name__ = 'res.user'

    send_own_changes = fields.Boolean('Send Own Changes')

    @classmethod
    def __setup__(cls):
        super(User, cls).__setup__()
        if not 'send_own_changes' in cls._preferences_fields:
            cls._preferences_fields.append('send_own_changes')

from django.conf import settings
from django.db import models

import amo
from apps.addons.models import Addon
from apps.editors.models import CannedResponse, EscalationQueue
from users.models import UserForeignKey


class AppCannedResponseManager(amo.models.ManagerBase):
    def get_query_set(self):
        qs = super(AppCannedResponseManager, self).get_query_set()
        return qs.filter(type=amo.CANNED_RESPONSE_APP)


class AppCannedResponse(CannedResponse):
    objects = AppCannedResponseManager()

    class Meta:
        proxy = True


class RereviewQueue(amo.models.ModelBase):
    addon = models.ForeignKey(Addon)

    class Meta:
        db_table = 'rereview_queue'

    @classmethod
    def flag(cls, addon, event, message=None):
        cls.objects.get_or_create(addon=addon)
        if message:
            amo.log(event, addon, addon.current_version,
                    details={'comments': message})
        else:
            amo.log(event, addon, addon.current_version)


class ThemeLock(amo.models.ModelBase):
    theme = models.OneToOneField('addons.Persona')
    reviewer = UserForeignKey()
    expiry = models.DateTimeField()

    class Meta:
        db_table = 'theme_locks'


def cleanup_queues(sender, instance, **kwargs):
    RereviewQueue.objects.filter(addon=instance).delete()
    EscalationQueue.objects.filter(addon=instance).delete()


# Don't add this signal in if we are not in the marketplace.
if settings.MARKETPLACE:
    models.signals.post_delete.connect(cleanup_queues, sender=Addon,
                                       dispatch_uid='queue-addon-cleanup')

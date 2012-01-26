import itertools
import random

import mock
from nose.tools import eq_

import amo
import amo.tests
from addons.models import Addon, AddonCategory, AddonRecommendation, Category
from bandwagon.models import (Collection, CollectionAddon, CollectionUser,
                              CollectionWatcher,
                              RecommendedCollection, FeaturedCollection)
from devhub.models import ActivityLog
from bandwagon import tasks
from users.models import UserProfile


def get_addons(c):
    q = c.addons.order_by('collectionaddon__ordering')
    return list(q.values_list('id', flat=True))


def activitylog_count(type):
    qs = ActivityLog.objects
    if type:
        qs = qs.filter(action=type.id)
    return qs.count()


class TestCollections(amo.tests.TestCase):
    fixtures = ('base/apps', 'base/users', 'base/addon_3615',
                'base/addon_10423_youtubesearch', 'base/addon_1833_yoono',
                'base/collections', 'bandwagon/test_models')

    def setUp(self):
        self.user = UserProfile.objects.create(username='uhhh', email='uh@hh')
        self.other = UserProfile.objects.exclude(id=self.user.id)[0]
        amo.set_user(self.user)

    def test_icon_url(self):

        # Has no icon
        c = Collection.objects.get(pk=512)
        assert c.icon_url.endswith('img/icons/collection.png')

        c.type = amo.COLLECTION_FAVORITES
        assert c.icon_url.endswith('img/icons/heart.png')

    def test_is_subscribed(self):
        c = Collection.objects.get(pk=512)
        c.following.create(user=self.user)
        assert c.is_subscribed(self.user)

    def test_translation_default(self):
        """Make sure we're getting strings from the default locale."""
        c = Collection.objects.get(pk=512)
        eq_(unicode(c.name), 'yay')

    def test_listed(self):
        """Make sure the manager's listed() filter works."""
        listed_count = Collection.objects.listed().count()
        # make a private collection
        private = Collection(
            name="Hello", uuid="4e2a1acc-39ae-47ec-956f-46e080ac7f69",
            listed=False, author=self.user)
        private.save()

        listed = Collection.objects.listed()
        eq_(len(listed), listed_count)

    def test_auto_uuid(self):
        c = Collection.objects.create(author=self.user)
        assert c.uuid != ''
        assert isinstance(c.uuid, basestring)

    def test_addon_index(self):
        c = Collection.objects.get(pk=80)
        c.author = self.user
        eq_(c.addon_index, None)
        ids = c.addons.values_list('id', flat=True)
        c.save()
        eq_(c.addon_index, Collection.make_index(ids))

    def test_recommended_collection(self):
        """RecommendedCollections automatically get type=rec."""
        c = RecommendedCollection.objects.create(author=self.user)
        eq_(c.type, amo.COLLECTION_RECOMMENDED)

    def test_set_addons(self):
        addons = list(Addon.objects.values_list('id', flat=True))
        c = Collection.objects.create(author=self.user)

        # Check insert.
        random.shuffle(addons)
        c.set_addons(addons)
        eq_(get_addons(c), addons)
        eq_(activitylog_count(amo.LOG.ADD_TO_COLLECTION), len(addons))

        # Check update.
        random.shuffle(addons)
        c.set_addons(addons)
        eq_(get_addons(c), addons)

        # Check delete.
        delete_cnt = len(addons) - 2
        addons = addons[:2]
        c.set_addons(addons)
        eq_(activitylog_count(amo.LOG.REMOVE_FROM_COLLECTION), delete_cnt)
        eq_(get_addons(c), addons)
        eq_(c.addons.count(), len(addons))

    def test_publishable_by(self):
        c = Collection.objects.create(author=self.other)
        CollectionUser(collection=c, user=self.user).save()
        eq_(c.publishable_by(self.user), True)

    def test_collection_meta(self):
        c = Collection.objects.create(author=self.user)
        eq_(c.addon_count, 0)
        c.add_addon(Addon.objects.all()[0])
        eq_(activitylog_count(amo.LOG.ADD_TO_COLLECTION), 1)
        c = Collection.objects.get(id=c.id)
        assert not c.from_cache
        eq_(c.addon_count, 1)

    def test_favorites_slug(self):
        c = Collection.objects.create(author=self.user, slug='favorites')
        eq_(c.type, amo.COLLECTION_NORMAL)
        eq_(c.slug, 'favorites~')

        c = Collection.objects.create(author=self.user, slug='favorites')
        eq_(c.type, amo.COLLECTION_NORMAL)
        eq_(c.slug, 'favorites~-1')

    def test_slug_dupe(self):
        c = Collection.objects.create(author=self.user, slug='boom')
        eq_(c.slug, 'boom')
        c.save()
        eq_(c.slug, 'boom')
        c = Collection.objects.create(author=self.user, slug='boom')
        eq_(c.slug, 'boom-1')
        c = Collection.objects.create(author=self.user, slug='boom')
        eq_(c.slug, 'boom-2')

    def test_watchers(self):
        def check(num):
            eq_(Collection.objects.get(id=512).subscribers, num)
        tasks.collection_watchers(512)
        check(0)
        CollectionWatcher.objects.create(collection_id=512, user=self.user)
        check(1)


class TestRecommendations(amo.tests.TestCase):
    fixtures = ['base/addon-recs']
    ids = [5299, 1843, 2464, 7661, 5369]

    def setUp(self):
        self.user = UserProfile.objects.create(username='uhhh', email='uh@hh')
        amo.set_user(self.user)

    @classmethod
    def expected_recs(self):
        scores, ranked = [], {}
        # Get all the add-on => rank pairs.
        for x in AddonRecommendation.scores(self.ids).values():
            scores.extend(x.items())
        # Sum up any dupes.
        groups = itertools.groupby(sorted(scores), key=lambda x: x[0])
        for addon, pairs in groups:
            ranked[addon] = sum(x[1] for x in pairs)
        addons = sorted(ranked.items(), key=lambda x: x[1], reverse=True)
        return [x[0] for x in addons if x[0] not in self.ids]

    def test_build_recs(self):
        recs = RecommendedCollection.build_recs(self.ids)
        eq_(recs, self.expected_recs())

    @mock.patch('bandwagon.models.AddonRecommendation.scores')
    def test_no_dups(self, scores):
        # The inner dict is the recommended addons for addon 7.
        scores.return_value = {7: {1: 5, 2: 3, 3: 4}}
        recs = RecommendedCollection.build_recs([7, 3, 8])
        # 3 should not be in the list since we already have it.
        eq_(recs, [1, 2])
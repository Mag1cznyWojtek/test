# encoding: utf-8

# Import Python libs
from __future__ import absolute_import, print_function, unicode_literals
import logging
import os
import time

# Import Salt Testing libs
from tests.support.paths import TMP_CONF_DIR, TMP
from tests.support.unit import TestCase, skipIf
from tests.support.mock import patch
from tests.support.case import SSHCase
from tests.support.helpers import (
    Webserver,
    SaveRequestsPostHandler,
    requires_sshd_server
)

# Import Salt libs
import salt.config
import salt.netapi

from salt.exceptions import (
    EauthAuthenticationError
)

log = logging.getLogger(__name__)


class NetapiClientTest(TestCase):
    eauth_creds = {
        'username': 'saltdev_auto',
        'password': 'saltdev',
        'eauth': 'auto',
    }

    def setUp(self):
        '''
        Set up a NetapiClient instance
        '''
        opts = salt.config.client_config(os.path.join(TMP_CONF_DIR, 'master'))
        self.netapi = salt.netapi.NetapiClient(opts)

    def tearDown(self):
        del self.netapi

    def test_local(self):
        low = {'client': 'local', 'tgt': '*', 'fun': 'test.ping'}
        low.update(self.eauth_creds)

        ret = self.netapi.run(low)
        self.assertEqual(ret, {'minion': True, 'sub_minion': True})

    def test_local_batch(self):
        low = {'client': 'local_batch', 'tgt': '*', 'fun': 'test.ping'}
        low.update(self.eauth_creds)

        ret = self.netapi.run(low)
        rets = []
        for _ret in ret:
            rets.append(_ret)
        self.assertIn({'sub_minion': True}, rets)
        self.assertIn({'minion': True}, rets)

    def test_local_async(self):
        low = {'client': 'local_async', 'tgt': '*', 'fun': 'test.ping'}
        low.update(self.eauth_creds)

        ret = self.netapi.run(low)

        # Remove all the volatile values before doing the compare.
        self.assertIn('jid', ret)
        ret.pop('jid', None)
        ret['minions'] = sorted(ret['minions'])
        self.assertEqual(ret, {'minions': sorted(['minion', 'sub_minion'])})

    def test_local_unauthenticated(self):
        low = {'client': 'local', 'tgt': '*', 'fun': 'test.ping'}

        with self.assertRaises(EauthAuthenticationError) as excinfo:
            ret = self.netapi.run(low)

    def test_wheel(self):
        low = {'client': 'wheel', 'fun': 'key.list_all'}
        low.update(self.eauth_creds)

        ret = self.netapi.run(low)

        # Remove all the volatile values before doing the compare.
        self.assertIn('tag', ret)
        ret.pop('tag')

        data = ret.get('data', {})
        self.assertIn('jid', data)
        data.pop('jid', None)

        self.assertIn('tag', data)
        data.pop('tag', None)

        ret.pop('_stamp', None)
        data.pop('_stamp', None)

        self.maxDiff = None
        self.assertTrue(set(['master.pem', 'master.pub']).issubset(set(ret['data']['return']['local'])))

    def test_wheel_async(self):
        # Give this test a little breathing room
        time.sleep(3)
        low = {'client': 'wheel_async', 'fun': 'key.list_all'}
        low.update(self.eauth_creds)

        ret = self.netapi.run(low)
        self.assertIn('jid', ret)
        self.assertIn('tag', ret)

    def test_wheel_unauthenticated(self):
        low = {'client': 'wheel', 'tgt': '*', 'fun': 'test.ping'}

        with self.assertRaises(EauthAuthenticationError) as excinfo:
            ret = self.netapi.run(low)

    @skipIf(True, 'This is not testing anything. Skipping for now.')
    def test_runner(self):
        # TODO: fix race condition in init of event-- right now the event class
        # will finish init even if the underlying zmq socket hasn't connected yet
        # this is problematic for the runnerclient's master_call method if the
        # runner is quick
        #low = {'client': 'runner', 'fun': 'cache.grains'}
        low = {'client': 'runner', 'fun': 'test.sleep', 'arg': [2]}
        low.update(self.eauth_creds)

        ret = self.netapi.run(low)

    @skipIf(True, 'This is not testing anything. Skipping for now.')
    def test_runner_async(self):
        low = {'client': 'runner', 'fun': 'cache.grains'}
        low.update(self.eauth_creds)

        ret = self.netapi.run(low)

    def test_runner_unauthenticated(self):
        low = {'client': 'runner', 'tgt': '*', 'fun': 'test.ping'}

        with self.assertRaises(EauthAuthenticationError) as excinfo:
            ret = self.netapi.run(low)


@requires_sshd_server
class NetapiSSHClientTest(SSHCase):
    eauth_creds = {
        'username': 'saltdev_auto',
        'password': 'saltdev',
        'eauth': 'auto',
    }

    def setUp(self):
        '''
        Set up a NetapiClient instance
        '''
        opts = salt.config.client_config(os.path.join(TMP_CONF_DIR, 'master'))
        self.netapi = salt.netapi.NetapiClient(opts)

        # Initialize salt-ssh
        self.run_function('test.ping')

    def tearDown(self):
        del self.netapi

    @classmethod
    def setUpClass(cls):
        cls.post_webserver = Webserver(handler=SaveRequestsPostHandler)
        cls.post_webserver.start()
        cls.post_web_root = cls.post_webserver.web_root
        cls.post_web_handler = cls.post_webserver.handler

    @classmethod
    def tearDownClass(cls):
        cls.post_webserver.stop()
        del cls.post_webserver

    def test_ssh(self):
        low = {'client': 'ssh', 'tgt': 'localhost', 'fun': 'test.ping'}
        low.update(self.eauth_creds)

        ret = self.netapi.run(low)

        self.assertIn('localhost', ret)
        self.assertEqual(ret['localhost']['return'], True)
        self.assertEqual(ret['localhost']['id'], 'localhost')
        self.assertEqual(ret['localhost']['fun'], 'test.ping')

    def test_ssh_unauthenticated(self):
        low = {'client': 'ssh', 'tgt': 'localhost', 'fun': 'test.ping'}

        with self.assertRaises(EauthAuthenticationError) as excinfo:
            ret = self.netapi.run(low)

    def test_ssh_unauthenticated_raw_shell_curl(self):

        fun = '-o ProxyCommand curl {0}'.format(self.post_web_root)
        low = {'client': 'ssh',
               'tgt': 'localhost',
               'fun': fun,
               'raw_shell': True}

        ret = None
        with self.assertRaises(EauthAuthenticationError) as excinfo:
            ret = self.netapi.run(low)

        self.assertEqual(self.post_web_handler.received_requests, [])
        self.assertEqual(ret, None)

    def test_ssh_unauthenticated_raw_shell_touch(self):

        badfile = os.path.join(TMP, 'badfile.txt')
        fun = '-o ProxyCommand touch {0}'.format(badfile)
        low = {'client': 'ssh',
               'tgt': 'localhost',
               'fun': fun,
               'raw_shell': True}

        ret = None
        with self.assertRaises(EauthAuthenticationError) as excinfo:
            ret = self.netapi.run(low)

        self.assertEqual(ret, None)
        self.assertFalse(os.path.exists('badfile.txt'))

    def test_ssh_authenticated_raw_shell_disabled(self):

        badfile = os.path.join(TMP, 'badfile.txt')
        fun = '-o ProxyCommand touch {0}'.format(badfile)
        low = {'client': 'ssh',
               'tgt': 'localhost',
               'fun': fun,
               'raw_shell': True}

        low.update(self.eauth_creds)

        ret = None
        with patch.dict(self.netapi.opts,
                        {'netapi_allow_raw_shell': False}):
            with self.assertRaises(EauthAuthenticationError) as excinfo:
                ret = self.netapi.run(low)

        self.assertEqual(ret, None)
        self.assertFalse(os.path.exists('badfile.txt'))

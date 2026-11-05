import json
import socket
import subprocess
import unittest
from unittest.mock import Mock,patch
from dafeiyu.research import public_address,target,fetch,_fetch,ResearchError


class NetworkTests(unittest.TestCase):
    def test_transition_multicast_and_special_ranges_rejected(self):
        for value in ['127.0.0.1','169.254.169.254','100.64.0.1','224.0.0.1','192.0.0.9','::1','ff02::1','fec0::1','::ffff:127.0.0.1','64:ff9b::7f00:1','64:ff9b:1::1','2002:7f00:1::1','2001::1']:
            with self.subTest(address=value):self.assertFalse(public_address(value))
        self.assertTrue(public_address('8.8.8.8'));self.assertTrue(public_address('2606:4700:4700::1111'))
    def test_prefers_checked_native_ipv4(self):
        addresses=[(socket.AF_INET6,socket.SOCK_STREAM,6,'',('2606:4700:4700::1111',443,0,0)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
        with patch('socket.getaddrinfo',return_value=addresses):self.assertEqual(target('https://example.com')[1],'8.8.8.8')
    def test_invalid_ports_are_clean_domain_errors(self):
        with self.assertRaises(ResearchError):target('https://example.com:invalid/path')
    def test_whole_fetch_deadline_includes_dns(self):
        with patch('dafeiyu.research.subprocess.run',side_effect=subprocess.TimeoutExpired('fetch',15)):
            with self.assertRaisesRegex(ResearchError,'15 秒'):fetch('https://example.com')
    def test_malformed_worker_result_never_becomes_source(self):
        child=subprocess.CompletedProcess('fetch',0,'[]','')
        with patch('dafeiyu.research.subprocess.run',return_value=child):
            with self.assertRaises(ResearchError):fetch('https://example.com')
    def test_redirect_to_private_address_rejected_before_second_request(self):
        response=Mock();response.status=302;response.getheader.return_value='https://127.0.0.1/private'
        connection=Mock();connection.getresponse.return_value=response
        from urllib.parse import urlsplit
        with patch('dafeiyu.research.target',side_effect=[(urlsplit('https://example.com'),'8.8.8.8'),ResearchError('private')]),patch('dafeiyu.research.PinnedHTTPS',return_value=connection):
            with self.assertRaises(ResearchError):_fetch('https://example.com')
        connection.request.assert_called_once();response.close.assert_called_once()


if __name__=='__main__':unittest.main()

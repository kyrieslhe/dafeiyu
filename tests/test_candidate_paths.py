from pathlib import Path
import tempfile
import unittest
from dafeiyu.coding import CodingError,apply,snapshot,safe_relative,validate_changes

class CandidatePaths(unittest.TestCase):
    def test_noncanonical_and_case_aliases_rejected(self):
        for value in ['a//b.py','a/./b.py','a.py/']:
            with self.assertRaises(CodingError):safe_relative(value)
        with self.assertRaises(CodingError):validate_changes({}, {'foo.py':'one','FOO.py':'two'})
        with self.assertRaises(CodingError):validate_changes({'café.py':'old'},{'cafe\u0301.py':'new'})
    def test_binary_candidate_never_overwrites_original(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home);project=root/'demo';project.mkdir();file=project/'image.png';file.write_bytes(b'original-binary')
            payload={'project':'demo','original_hashes':{},'files':{'image.png':'model text'}}
            with self.assertRaises(CodingError):apply(root,payload)
            self.assertEqual(file.read_bytes(),b'original-binary')
    def test_non_utf8_source_is_not_silently_omitted(self):
        with tempfile.TemporaryDirectory() as home:
            project=Path(home);(project/'legacy.py').write_bytes(b'\xff\xfe')
            with self.assertRaises(CodingError):snapshot(project)
    def test_normal_text_change_allowed(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home);project=root/'demo';project.mkdir();file=project/'main.py';file.write_text('old')
            from dafeiyu.coding import digest
            apply(root,{'project':'demo','original_hashes':{'main.py':digest(b'old')},'files':{'main.py':'new'}})
            self.assertEqual(file.read_text(),'new')

if __name__=='__main__':unittest.main()

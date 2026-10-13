import unittest
from core.device import DeviceError, validate_volume, resolve_volume


class DeviceTests(unittest.TestCase):
    def info(self, name='Chosen SSD', uuid='identity'):
        return {'MountPoint': '/Volumes/' + name, 'VolumeUUID': uuid,
                'FilesystemType': 'exfat', 'Internal': False, 'Writable': True,
                'ReadOnlyVolume': False, 'TotalSize': 100 * 1024**3}

    def test_identity_survives_name_change(self):
        volume = resolve_volume('identity', lambda _: self.info('Renamed'))
        self.assertEqual(volume['mount'], '/Volumes/Renamed')

    def test_same_name_other_uuid_is_rejected(self):
        with self.assertRaises(DeviceError):
            resolve_volume('identity', lambda _: self.info(uuid='other'))

    def test_unsupported_or_internal_volume_is_rejected(self):
        for change in ({'Internal': True}, {'FilesystemType': 'msdos'}, {'ReadOnlyVolume': True}):
            with self.subTest(change=change), self.assertRaises(DeviceError):
                validate_volume({**self.info(), **change})

    def test_current_diskutil_writable_key_is_sufficient_without_readonlyvolume(self):
        info = self.info()
        del info['ReadOnlyVolume']
        self.assertEqual(validate_volume(info)['uuid'], 'identity')
        del info['Writable']
        with self.assertRaises(DeviceError):
            validate_volume(info)

import json
import pytest


pytestmark = pytest.mark.usefixtures("master", "minion", "minion_key_accepted")


def pytest_generate_tests(metafunc):
    tags = metafunc.config.getini('TAGS')
    VERSIONS = [
        ['0.2-1', '0.2-1', 0],
        ['0.2-1.0', '0.2-1', 1],
        ['0.2.0-1', '0.2-1', 1],
        ['0.2-1', '1:0.2-1', -1],
        ['1:0.2-1', '0.2-1', 1],
    ]
    if 'sles12' in tags or 'sles12sp1' in tags:
        VERSIONS += [
            ['0.2-1', '0.2~beta1-1', 1],
            ['0.2~beta2-1', '0.2-1', -1]
        ]
    else:
        VERSIONS += [
            ['0.2-1', '0.2~beta1-1', -1],
            ['0.2~beta2-1', '0.2-1', 1]
        ]
    metafunc.parametrize(
        "params", VERSIONS, ids=lambda it: '{0}:{1}:{2}'.format(*it))


@pytest.mark.tags('sles')
def test_pkg_compare(params, minion):
    info = minion['container'].get_suse_release()
    major, minor = info['VERSION'], info['PATCHLEVEL']
    [ver1, ver2, expected] = params
    command = "salt-call pkg.version_cmp {0} --output=json -l quiet".format(
        ' '.join([ver1, ver2])
    )
    raw = minion['container'].run(command)
    assert json.loads(raw)['local'] == expected

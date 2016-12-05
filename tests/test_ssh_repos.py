import pytest
import json
from saltcontainers.factories import ContainerFactory

USER = "root"
PASSWORD = "admin123"
SSH = "salt-ssh -i --out json --key-deploy --passwd {0} target {1}".format(PASSWORD, '{0}')

@pytest.fixture(scope='module')
def module_config(request, container):
    return {
        "masters": [
            {
                "config": {
                    "container__config__salt_config__extra_configs": {
                        "thin_extra_mods": {
                            "thin_extra_mods": "msgpack"
                        }
                    },
                    "container__config__salt_config__apply_states": {
                        "top": "tests/sls/ssh/top.sls",
                        "ssh": "tests/sls/ssh/ssh.sls"
                    },
                    "container__config__salt_config__roster": {
                        "target": {
                            "host": container["ip"],
                            "user": USER,
                            "password": PASSWORD
                        }
                    }
                }
            }
        ]
    }


@pytest.fixture(scope="module")
def container(request, salt_root, docker_client):
    obj = ContainerFactory(
        config__docker_client=docker_client,
        config__image=request.config.getini('IMAGE'),
        config__salt_config=None)

    obj.run('ssh-keygen -t rsa -f /etc/ssh/ssh_host_rsa_key -q -N ""')
    obj.run('ssh-keygen -t ecdsa -f /etc/ssh/ssh_host_ecdsa_key -q -N ""')
    obj.run('ssh-keygen -t ed25519 -f /etc/ssh/ssh_host_ed25519_key -q -N ""')
    obj.run('./tests/scripts/chpasswd.sh {}:{}'.format(USER, PASSWORD))
    obj.run('/usr/sbin/sshd')
    obj.run('zypper --non-interactive rm salt')  # Remove salt from the image!!

    request.addfinalizer(obj.remove)
    return obj


def _cmd(setup, cmd):
    '''
    Get container from the setup and run given command on it.

    :param setup: Setup
    :param cmd: An SSH command
    '''
    config, initconfig = setup
    master = config['masters'][0]['fixture']
    return json.loads(master['container'].run(SSH.format(cmd)))


@pytest.mark.tags('sles')
def test_pkg_owner(setup):
    '''
    Test pkg.owner
    '''
    #assert _cmd(setup, "pkg.owner /etc/zypp")['target'] == 'libzypp'


@pytest.mark.tags('sles')
def test_pkg_list_products(setup):
    '''
    List test products
    '''
    products = _cmd(setup, "pkg.list_products")['target']
    for prod in products:
        if prod['productline'] == 'sles':
            assert prod['productline'] == 'sles'
            assert prod['name'] == 'SLES'
            assert prod['vendor'] == 'SUSE'
            assert prod['isbase']
            assert prod['installed']
            break
        else:
            raise Exception("Product not found")
    
def test_pkg_search(setup):
    assert 'test-package-zypper' in _cmd(setup, "pkg.search test-package")['target']


def test_pkg_repo(setup):
    assert _cmd(setup, 'pkg.list_repos')['target']['testpackages']['enabled']

def test_pkg_mod_repo(setup):
    assert not _cmd(setup, 'pkg.mod_repo testpackages enabled=false')['target']['enabled']
    assert _cmd(setup, 'pkg.mod_repo testpackages enabled=true')['target']['enabled']


def test_pkg_del_repo(setup):
    msg = "Repository 'testpackages' has been removed."
    out = _cmd(setup, 'pkg.del_repo testpackages')['target']
    assert out['message'] == msg
    assert out['testpackages']


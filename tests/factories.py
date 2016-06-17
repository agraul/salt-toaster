import os
import yaml
import string
import factory
import factory.fuzzy
from docker import Client
from models import ContainerModel, MasterModel, MinionModel
from utils import get_docker_build_params


class BaseFactory(factory.Factory):

    class Meta:
        model = dict
        strategy = factory.BUILD_STRATEGY


class DockerClientFactory(factory.StubFactory):

    @classmethod
    def stub(cls, **kwargs):
        return Client(base_url='unix://var/run/docker.sock')


class ImageFactory(BaseFactory):
    version = os.environ.get('VERSION', 'sles12sp1')
    flavor = os.environ.get('FLAVOR', 'products')
    params = factory.LazyAttribute(
        lambda o: get_docker_build_params(o.version, o.flavor, o.path))
    tag = factory.LazyAttribute(lambda o: o.params['tag'])
    dockerfile = factory.LazyAttribute(lambda o: o.params['dockerfile'])
    path = factory.LazyAttribute(lambda o: os.getcwd() + '/docker/')
    docker_client = factory.LazyAttribute(
        lambda o: o.factory_parent.factory_parent.docker_client)
    path = os.getcwd() + '/docker/'
    build_image = True

    @classmethod
    def build(cls, **kwargs):
        obj = super(ImageFactory, cls).build(**kwargs)
        if obj['build_image']:
            output = obj['docker_client'].build(path=obj['path'], **obj['params'])
            for item in output:
                print item.values()[0]
        return obj


class SaltConfigFactory(BaseFactory):

    tmpdir = None
    root = factory.LazyAttribute(lambda o: o.tmpdir.mkdir(o.factory_parent.name))
    conf_type = None
    config = {}
    pillar = {}
    docker_client = None
    id = None

    @factory.post_generation
    def post(obj, create, extracted, **kwargs):
        assert kwargs['id']
        obj['id'] = kwargs['id']
        config_file = obj['root'] / obj['conf_type']
        main_config = {
            'include': '{0}.d/*'.format(obj['conf_type'])
        }
        if obj['conf_type'] in ['minion', 'proxy']:
            main_config['id'] = obj['id']

        config_file.write(
            yaml.safe_dump(main_config, default_flow_style=False))

        config_path = obj['root'].mkdir('{0}.d'.format(obj['conf_type']))
        for name, config in obj['config'].items():
            config_file = config_path / '{0}.conf'.format(name)
            config_file.write(yaml.safe_dump(config, default_flow_style=False))

        pillar_path = obj['root'].mkdir('pillar')
        for name, content in obj['pillar'].items():
            sls_file = pillar_path / '{0}.sls'.format(name)
            sls_file.write(yaml.safe_dump(content, default_flow_style=False))


class ContainerConfigFactory(BaseFactory):
    name = factory.fuzzy.FuzzyText(
        length=5, prefix='container_', chars=string.ascii_letters)
    salt_config = factory.SubFactory(SaltConfigFactory)
    image_obj = factory.SubFactory(ImageFactory)
    image = factory.LazyAttribute(lambda o: o.image_obj['tag'])
    command = '/bin/bash'
    environment = dict()
    tty = True
    stdin_open = True
    working_dir = "/salt-toaster/"
    ports = [4000, 4506]
    volumes = factory.LazyAttribute(
        lambda obj: [obj.salt_config['root'].strpath, os.getcwd()]
    )
    host_config = factory.LazyAttribute(
        lambda obj: obj.factory_parent.docker_client.create_host_config(
            port_bindings={},
            binds={
                obj.salt_config['root'].strpath: {
                    'bind': '/etc/salt/',
                    'mode': 'rw',
                },
                os.getcwd(): {
                    'bind': "/salt-toaster/",
                    'mode': 'rw'
                }
            }
        )
    )

    class Meta:
        exclude = ['image_obj', 'salt_config']


class ContainerFactory(BaseFactory):

    docker_client = None
    config = factory.SubFactory(ContainerConfigFactory)
    ip = None

    class Meta:
        model = ContainerModel

    @classmethod
    def build(cls, **kwargs):
        obj = super(ContainerFactory, cls).build(**kwargs)
        obj['docker_client'].create_container(**obj['config'])
        obj['docker_client'].start(obj['config']['name'])
        data = obj['docker_client'].inspect_container(obj['config']['name'])
        obj['ip'] = data['NetworkSettings']['IPAddress']
        return obj


class MasterFactory(BaseFactory):
    container = factory.SubFactory(
        ContainerFactory,
        config__name=factory.fuzzy.FuzzyText(
            length=5, prefix='master_', chars=string.ascii_letters)
    )

    class Meta:
        model = MasterModel

    @classmethod
    def build(cls, **kwargs):
        obj = super(MasterFactory, cls).build(**kwargs)
        docker_client = obj['container']['docker_client']
        res = docker_client.exec_create(
            obj['container']['config']['name'],
            cmd='salt-master -d -l debug'
        )
        docker_client.exec_start(res['Id'])
        return obj


class MinionFactory(BaseFactory):
    container = factory.SubFactory(
        ContainerFactory,
        config__name=factory.fuzzy.FuzzyText(
            length=5, prefix='minion_', chars=string.ascii_letters)
    )
    cmd = 'salt-minion -d -l debug'

    class Meta:
        model = MinionModel

    @classmethod
    def build(cls, **kwargs):
        obj = super(MinionFactory, cls).build(**kwargs)
        docker_client = obj['container']['docker_client']
        res = docker_client.exec_create(
            obj['container']['config']['name'], obj['cmd']
        )
        output = docker_client.exec_start(res['Id'])
        assert 'executable file not found' not in output
        return obj

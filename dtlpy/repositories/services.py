import datetime
import logging
import json
import os

from urllib.parse import urlencode

from .. import miscellaneous, exceptions, entities, repositories, assets
from ..__version__ import version as __version__

logger = logging.getLogger(name=__name__)


class Services:
    def __init__(self, client_api, project=None, package=None):
        self._client_api = client_api
        self._package = package
        self._project = project

    ############
    # entities #
    ############
    @property
    def package(self):
        if self._package is None:
            raise exceptions.PlatformException(
                error='2001',
                message='Cannot perform action WITHOUT package entity in services repository. Please set a package')
        assert isinstance(self._package, entities.Package)
        return self._package

    @package.setter
    def package(self, package):
        if not isinstance(package, entities.Package):
            raise ValueError('Must input a valid package entity')
        self._package = package

    @property
    def project(self):
        if self._project is None:
            # try to get from package
            if self._package is not None:
                self._project = self._package._project

        if self._project is None:
            # try to get checked out project
            project = self._client_api.state_io.get('project')
            if project is not None:
                self._project = entities.Project.from_json(_json=project, client_api=self._client_api)
        if self._project is None:
            raise exceptions.PlatformException(
                error='2001',
                message='Cannot perform action WITHOUT Project entity in services repository. Please set a project')
        return self._project

    @project.setter
    def project(self, project):
        if not isinstance(project, entities.Project):
            raise ValueError('Must input a valid Project entity')
        self._project = project

    def open_in_web(self, service=None, service_id=None, service_name=None):
        if service is None:
            service = self.get(service_id=service_id, service_name=service_name)
        self._client_api._open_in_web(resource_type='service', project_id=service.project_id,
                                      package_id=service.package_id, service_id=service.id)

    def __get_from_cache(self):
        service = self._client_api.state_io.get('service')
        if service is not None:
            service = entities.Service.from_json(_json=service, client_api=self._client_api, project=self._project,
                                                 package=self._package)
        return service

    def checkout(self, service=None, service_name=None, service_id=None):
        """
        Check-out a service
        :param service_id:
        :param service_name:
        :param service: Service entity
        :return:
        """
        if service is None:
            service = self.get(service_name=service_name, service_id=service_id)
        self._client_api.state_io.put('service', service.to_json())
        logger.info('Checked out to service {}'.format(service.name))

    ###########
    # methods #
    ###########
    def get(self, service_name=None, service_id=None, checkout=False):
        """
        Get service

        :param checkout:
        :param service_name: optional - search by name
        :param service_id: optional - search by id
        :return: Service object
        """
        if service_id is not None:
            success, response = self._client_api.gen_request(
                req_type="get",
                path="/services/{}".format(service_id)
            )
            if not success:
                raise exceptions.PlatformException(response)
            service = entities.Service.from_json(client_api=self._client_api,
                                                 _json=response.json(),
                                                 package=self._package,
                                                 project=self._project)
        elif service_name is not None:
            services = self.list(name=service_name)
            if len(services) > 1:
                raise exceptions.PlatformException('404', 'More than one service with same name.')
            elif len(services) == 0:
                raise exceptions.PlatformException('404', 'Service not found: {}.'.format(service_name))
            service = services[0]
        else:
            service = self.__get_from_cache()
            if service is None:
                raise exceptions.PlatformException('404', 'No service found in state, please checkout a service.')

        assert isinstance(service, entities.Service)
        if checkout:
            self.checkout(service=service)
        return service

    def list(self, name=None, project_id=None, package_id=None):
        """
        List project services
        :return:
        """
        url = '/services'
        query_params = {
            'name': name
        }

        # either project or service
        if project_id is None and self._project is not None:
            project_id = self._project.id
        if package_id is None and self._package is not None:
            package_id = self._package.id

        if package_id is not None:
            query_params['packageId'] = package_id
        if project_id is not None:
            query_params['projects'] = project_id

        url += '?{}'.format(urlencode({key: val for key, val in query_params.items() if val is not None}, doseq=True))

        # request
        success, response = self._client_api.gen_request(req_type='get',
                                                         path=url)
        if not success:
            raise exceptions.PlatformException(response)

        services_json = response.json()['items']
        jobs = [None for _ in range(len(services_json))]
        pool = self._client_api.thread_pools(pool_name='entity.create')

        # return triggers list
        for i_service, service in enumerate(services_json):
            jobs[i_service] = pool.apply_async(entities.Service._protected_from_json,
                                               kwds={'client_api': self._client_api,
                                                     '_json': service,
                                                     'package': self._package,
                                                     'project': self._project})
        # wait for all jobs
        _ = [j.wait() for j in jobs]
        # get all results
        results = [j.get() for j in jobs]
        # log errors
        _ = [logger.warning(r[1]) for r in results if r[0] is False]
        # return good jobs
        return miscellaneous.List([r[1] for r in results if r[0] is True])

    def status(self, service_name=None, service_id=None):
        if service_id is None:
            if service_name is None:
                raise exceptions.PlatformException(error='400',
                                                   message='must input "service_name" or "service_id" to get status')
            service = self.get(service_name=service_name)
            service_id = service.id
        # request
        # request
        success, response = self._client_api.gen_request(req_type="get",
                                                         path="/services/{}/status".format(service_id))
        if not success:
            raise exceptions.PlatformException(response)
        return response.json()

    def _create(self, service_name=None, package=None, module_name=None, bot=None, revision=None, init_input=None,
                runtime=None, pod_type=None, project_id=None, sdk_version=None, agent_versions=None, verify=True,
                driver_id=None):
        """
        Create service entity
        :param verify:
        :param agent_versions:
        :param sdk_version:
        :param project_id:
        :param pod_type:
        :param runtime:
        :param init_input:
        :param driver_id:
        :param bot: bot user that weill run the package
        :param revision: optional - int - package revision - default=latest
        :param package:
        :param service_name:
        :return:
        """
        if agent_versions is None:
            if sdk_version is None:
                sdk_version = __version__
            agent_versions = {
                "dtlpy": sdk_version,
                "verify": verify
            }

        if self._project is None and project_id is None:
            raise exceptions.PlatformException('400', 'Please provide project id')
        elif project_id is None:
            project_id = self._project.id

        if package is None:
            if self._package is None:
                raise exceptions.PlatformException('400', 'Please provide param package')
            package = self._package
        if module_name is None:
            module_name = entities.DEFAULT_PACKAGE_MODULE.name
        if service_name is None:
            service_name = 'default-service'

        if not isinstance(init_input, dict):
            if init_input is None:
                init_input = dict()
            else:
                init_params = dict()
                if not isinstance(init_input, list):
                    init_input = [init_input]
                for param in init_input:
                    if isinstance(param, entities.FunctionIO):
                        init_params.update(param.to_json(resource='service'))
                    else:
                        raise exceptions.PlatformException('400', 'Unknown type of init params')
                init_input = init_params

        if bot is None:
            if self._project is None:
                raise exceptions.PlatformException(error='2001',
                                                   message='Need project entity or bot to perform this action')
            bots = self._project.bots.list()
            if len(bots) == 0:
                logger.info('Bot not found for project. Creating a default bot')
                bot = self._project.bots.create(name='default')
            else:
                bot = bots[0]
                if len(bots) > 1:
                    logger.debug('More than one bot users. Choosing first. email: {}'.format(bots[0].email))

        if isinstance(bot, str):
            bot_email = bot
        elif isinstance(bot, entities.Bot) or isinstance(bot, entities.User):
            bot_email = bot.email
        else:
            raise ValueError('input "bot" must be a str or a Bot type, got: {}'.format(type(bot)))

        # payload
        payload = {'name': service_name,
                   'projectId': project_id,
                   'packageId': package.id,
                   'initParams': init_input,
                   'botUserName': bot_email,
                   'versions': agent_versions,
                   'moduleName': module_name,
                   'driverId': driver_id}

        # revision
        if isinstance(revision, int):
            payload['packageRevision'] = revision

        if runtime is not None:
            payload['runtime'] = runtime
        else:
            payload['runtime'] = {'gpu': False,
                                  'numReplicas': 1}

        if pod_type is None:
            if 'gpu' in payload['runtime'] and payload['runtime']['gpu']:
                pod_type = 'gpu-k80-s'
            else:
                pod_type = 'regular-s'

        if 'podType' not in payload['runtime']:
            payload['runtime']['podType'] = pod_type

        # request
        success, response = self._client_api.gen_request(req_type='post',
                                                         path='/services',
                                                         json_req=payload)

        # exception handling
        if not success:
            raise exceptions.PlatformException(response)

        # return entity
        return entities.Service.from_json(_json=response.json(),
                                          client_api=self._client_api,
                                          package=package,
                                          project=self._project)

    def delete(self, service_name=None, service_id=None):
        """
        Delete Service object

        :param service_id: by id
        :param service_name: by name
        :return: True
        """
        # get bby name
        if service_id is None:
            if service_name is None:
                raise exceptions.PlatformException('400', 'Must provide either service id or service name')
            else:
                services = self.list()
                for service in services:
                    if service.name == service_name:
                        service_id = service.id
        # request
        success, response = self._client_api.gen_request(
            req_type="delete",
            path="/services/{}".format(service_id)
        )
        if not success:
            raise exceptions.PlatformException(response)
        return True

    def update(self, service):
        """
        Update Service changes to platform
        :param service: Service entity
        :return: Service entity
        """
        assert isinstance(service, entities.Service)

        # payload
        payload = service.to_json()

        # request
        success, response = self._client_api.gen_request(req_type='patch',
                                                         path='/services/{}'.format(service.id),
                                                         json_req=payload)

        # exception handling
        if not success:
            raise exceptions.PlatformException(response)

        # return entity
        if self._package is not None:
            package = self._package
        else:
            package = service._package

        return entities.Service.from_json(_json=response.json(),
                                          client_api=self._client_api,
                                          package=package,
                                          project=self._project)

    def log(self, service, size=None, checkpoint=None, start=None, end=None):
        """
        Get service logs

        :param end: iso format time
        :param start: iso format time
        :param checkpoint:
        :param size:
        :param service: Service entity
        :return: Service entity
        """
        assert isinstance(service, entities.Service)

        payload = {
            'direction': 'asc'
        }

        if size is not None:
            payload['size'] = size

        if checkpoint is not None:
            payload['checkpoint'] = checkpoint

        if start is not None:
            payload['start'] = start
        else:
            payload['start'] = datetime.datetime(datetime.date.today().year,
                                                 datetime.date.today().month,
                                                 datetime.date.today().day,
                                                 0,
                                                 0,
                                                 0).isoformat()

        if end is not None:
            payload['end'] = end

        # request
        success, response = self._client_api.gen_request(req_type='post',
                                                         path='/services/{}/logs'.format(service.id),
                                                         json_req=payload)

        # exception handling
        if not success:
            raise exceptions.PlatformException(response)

        return ServiceLog(_json=response.json(),
                          service=service,
                          services=self,
                          start=payload['start'])

    def execute(self, service=None, service_id=None, service_name=None, sync=False, execution_input=None,
                function_name=None, resource=None, item_id=None, dataset_id=None, annotation_id=None):
        if service is None:
            service = self.get(service_id=service_id, service_name=service_name)
        execution = repositories.Executions(service=service,
                                            client_api=self._client_api,
                                            project=self._project).create(service_id=service.id,
                                                                          sync=sync,
                                                                          execution_input=execution_input,
                                                                          function_name=function_name,
                                                                          resource=resource,
                                                                          item_id=item_id,
                                                                          dataset_id=dataset_id,
                                                                          annotation_id=annotation_id)
        return execution

    def deploy(self, service_name=None, package=None, bot=None, revision=None, init_input=None, runtime=None,
               pod_type=None, sdk_version=None, agent_versions=None, verify=True, checkout=False, module_name=None,
               project_id=None, driver_id=None):
        """
        Deploy service

        :param project_id:
        :param module_name:
        :param checkout:
        :param verify:
        :param pod_type:
        :param service_name: name
        :param package: package entity
        :param bot: bot email
        :param revision: version
        :param init_input: config to run at startup
        :param runtime: runtime resources
        :param driver_id:
        :param agent_versions: - dictionary - - optional -versions of sdk, agent runner and agent proxy
        :param sdk_version:  - optional - string - sdk version
        :return:
        """
        if init_input is not None and not isinstance(init_input, dict):
            if not isinstance(init_input, list):
                init_input = [init_input]

            if isinstance(init_input[0], entities.FunctionIO):
                params = dict()
                for i_param, param in enumerate(init_input):
                    params[param.name] = param.value
                init_input = params
            else:
                raise exceptions.PlatformException(
                    error='400',
                    message='Unknown init_input type. expecting list or dict, got: {}'.format(type(init_input)))

        services = self.list(name=service_name, project_id=project_id)
        if len(services) > 1:
            raise exceptions.PlatformException('400',
                                               'More than 1 service by this name are associated with this user. '
                                               'Please provide project_id')
        elif len(services) > 0:
            service = services[0]
            if runtime is not None:
                service.runtime = runtime
            if init_input is not None:
                service.init_input = init_input
            if revision is not None:
                service.package_revision = revision
            if agent_versions is not None:
                service.versions = agent_versions
            if driver_id is not None:
                service.driver_id = driver_id
            service = self.update(service=service)
        else:
            service = self._create(service_name=service_name,
                                   package=package,
                                   bot=bot,
                                   revision=revision,
                                   init_input=init_input,
                                   runtime=runtime,
                                   pod_type=pod_type,
                                   sdk_version=sdk_version,
                                   agent_versions=agent_versions,
                                   verify=verify,
                                   module_name=module_name,
                                   driver_id=driver_id)
        if checkout:
            self.checkout(service=service)
        return service

    def deploy_from_local_folder(self, cwd=None, service_file=None, bot=None, checkout=False):
        """
        Deploy from local folder
        :param checkout:
        :param bot:
        :return:

        :param cwd: optional - package working directory. Default=cwd
        :param service_file: optional - service file. Default=None
        """
        # get cwd and service.json path
        if cwd is None:
            cwd = os.getcwd()
        if service_file is None:
            service_file = os.path.join(cwd, assets.paths.SERVICE_FILENAME)

        # load service json
        if os.path.isfile(service_file):
            with open(service_file, 'r') as f:
                service_json = json.load(f)
            service_triggers = service_json.get('triggers', list())
        else:
            raise exceptions.PlatformException(error='400',
                                               message='Could not find service.json in path: {}'.format(cwd))

        # get package
        package_name = service_json.get('packageName', None)
        packages = repositories.Packages(client_api=self._client_api, project=self._project)
        if package_name is None:
            package = packages.get()
        else:
            package = packages.get(package_name=package_name)

        name = service_json.get('name', None)
        revision = service_json.get('revision', package.version)
        init_input = service_json.get('initParams', dict())
        runtime = service_json.get('runtime', dict())
        sdk_version = service_json.get('version', None)
        agent_versions = service_json.get('versions', None)
        verify = service_json.get('verify', True)
        module_name = service_json.get('module_name', None)

        service = self.deploy(bot=bot,
                              service_name=name,
                              package=package,
                              revision=revision,
                              runtime=runtime,
                              init_input=init_input,
                              sdk_version=sdk_version,
                              agent_versions=agent_versions,
                              verify=verify,
                              checkout=checkout,
                              module_name=module_name)

        triggers = repositories.Triggers(client_api=self._client_api, project=self._project)
        for trigger in service_triggers:
            name = trigger.get('name', None)
            filters = trigger.get('filter', dict())
            resource = trigger['resource']
            actions = trigger.get('actions', list())
            active = trigger.get('active', True)
            execution_mode = trigger.get('executionMode', None)
            function_name = trigger.get('function', None)

            triggers.create(service_id=service.id,
                            name=name,
                            filters=filters,
                            resource=resource,
                            actions=actions,
                            active=active,
                            execution_mode=execution_mode,
                            function_name=function_name)

        logging.debug('Successfully deployed!')
        return service

    def deploy_pipeline(self, service_json_path=None, project=None, bot=None):
        """
        Deploy pipeline

        :param bot:
        :param project:
        :param service_json_path:
        :return: True
        """
        # project
        if project is None:
            project = self._project

        # get service file
        if service_json_path is None:
            service_json_path = os.getcwd()

        if not service_json_path.endswith('.json'):
            service_json_path = os.path.join(service_json_path, 'service.json')
            if not os.path.isfile(service_json_path):
                raise exceptions.PlatformException('404', 'File not exist: {}'.format(service_json_path))

        # get existing project's services and triggers
        project_triggers = {trigger.name: trigger for trigger in project.triggers.list()}
        project_services = {service.name: service for service in project.services.list()}
        project_packages = {package.name: package for package in project.packages.list()}

        # load file
        with open(service_json_path, 'r') as f:
            service_json = json.load(f)

        # build
        for service_input in service_json:
            # get package
            if service_input['package'] in project_packages:
                package = project_packages[service_input['package']]
            else:
                raise exceptions.PlatformException('404', 'Package not found, package name: {}'.format(
                    service_input['package']))

            sdk_version = service_json.get('version', None)
            agent_versions = service_json.get('versions', None)
            verify = service_json.get('verify', True)
            runtime = service_input.get('runtime', None)
            init_input = service_input.get('initParams', None)
            module_name = service_input.get('module_name', None)
            driver_id = service_input.get('driverId', None)
            # create or update service
            if service_input['name'] in project_services:
                service = project_services[service_input['name']]
                service.runtime = runtime
                service.init_input = init_input
                service = project.services.update(service=service)
                service.version = sdk_version
                service.versions = agent_versions
                service.verify = verify
                service.driver_id = driver_id
                project_services[service.name] = service

            else:
                service = self._create(package=package,
                                       bot=bot,
                                       service_name=service_input['name'],
                                       runtime=runtime,
                                       init_input=init_input,
                                       agent_versions=agent_versions,
                                       sdk_version=sdk_version,
                                       verify=verify,
                                       module_name=module_name,
                                       driver_id=driver_id)
                project_services[service.name] = service

            service_triggers = {trigger: project_triggers[trigger] for trigger in project_triggers if
                                project_triggers[trigger].service_id == service.id}

            # create or update triggers
            if 'triggers' in service_input:
                for trigger_input in service_input['triggers']:
                    if trigger_input['name'] in service_triggers:
                        trigger = project_triggers[trigger_input['name']]
                        trigger.resource = trigger_input.get('resource', trigger.resource)
                        trigger.active = trigger_input.get('active', trigger.active)
                        trigger.actions = trigger_input.get('actions', trigger.actions)
                        trigger.filters = trigger_input.get('filters', trigger.filters)
                        trigger.execution_mode = trigger_input.get('executionMode', trigger.execution_mode)
                        trigger.function_name = trigger_input.get('function', None)
                        trigger = trigger.update()
                        project_triggers[trigger.name] = trigger
                    else:
                        trigger = project.triggers.create(service_ids=[service.id],
                                                          resource=trigger_input.get('resource', None),
                                                          active=trigger_input.get('active', None),
                                                          actions=trigger_input.get('actions', None),
                                                          filters=trigger_input.get('filters', None),
                                                          function_name=trigger_input.get('function', None),
                                                          execution_mode=trigger_input.get('executionMode', None))
                        project_triggers[trigger.name] = trigger

        print('File deployed successfully!')
        return True

    def tear_down(self, service_json_path=None, project=None):
        """
        Tear down a pipeline

        :param project:
        :param service_json_path:
        :return:
        """
        # project
        if project is None:
            project = self._project

        # get service file
        if service_json_path is None:
            service_json_path = os.getcwd()

        if not service_json_path.endswith('.json'):
            service_json_path = os.path.join(service_json_path, 'service.json')
            if not os.path.isfile(service_json_path):
                raise exceptions.PlatformException('404', 'File not exist: {}'.format(service_json_path))

        # get existing project's services and triggers
        project_triggers = {trigger.name: trigger for trigger in project.triggers.list()}
        project_services = {service.name: service for service in project.services.list()}

        with open(service_json_path, 'r') as f:
            service_json = json.load(f)

        # tear down
        for service_input in service_json:
            # delete service
            if service_input['name'] in project_services:
                service = project_services[service_input['name']]
                service.delete()

            # delete triggers
            if 'triggers' in service_input:
                for trigger_input in service_input['triggers']:
                    if trigger_input['name'] in project_triggers:
                        trigger = project_triggers[trigger_input['name']]
                        trigger.delete()

        print('File torn down successfully!')
        return True

    @staticmethod
    def generate_services_json(path=None):
        if path is None:
            path = os.getcwd()
        path = os.path.join(path, assets.paths.SERVICE_FILENAME)
        with open(assets.paths.ASSETS_SERVICE_FILEPATH, 'r') as f:
            service_file = json.load(f)
        with open(path, 'w') as f:
            json.dump(service_file, f, indent=2)
        return path


class ServiceLog:
    """
    Service Log
    """

    def __init__(self, _json, service, services, start=None):
        self.logs = _json.get('logs', dict())
        self.checkpoint = _json.get('checkpoint', None)
        self.stop = _json.get('stop', False)
        self.service = service
        self.services = services
        self.start = start

    def get_next_log(self):
        log = self.services.log(service=self.service, checkpoint=self.checkpoint, start=self.start)
        self.logs = log.logs
        self.checkpoint = log.checkpoint
        self.stop = log.stop

    def __iter__(self):
        while not self.stop:
            for log in self.logs:
                yield '{}: {}'.format(log.get('timestamp', self.start), log.get('message', ''))
            self.get_next_log()

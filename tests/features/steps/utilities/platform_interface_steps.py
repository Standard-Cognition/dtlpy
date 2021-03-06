import random
import behave
import time
import jwt
import os
import dtlpy as dl
import numpy as np
try:
    # for local import
    from tests.env_from_git_branch import get_env_from_git_branch
except ImportError:
    # for remote import
    from env_from_git_branch import get_env_from_git_branch


@behave.given('Platform Interface is initialized as dlp and Environment is set according to git branch')
def before_all(context):
    if hasattr(context.feature, 'dataloop_feature_dl'):
        context.dl = context.feature.dataloop_feature_dl
    else:
        # get cookie name
        feature_name = context.feature.name.replace(' ', '_')
        api_counter_name = 'api_counter_{}.json'.format(feature_name)
        api_counter_filepath = os.path.join(os.path.dirname(dl.client_api.cookie_io.COOKIE), api_counter_name)
        # set counter
        dl.client_api.set_api_counter(api_counter_filepath)

        # set context for run
        dl.client_api.verbose.print_all_responses = True
        context.dl = dl

        # reset api counter
        context.dl.client_api.calls_counter.on()
        context.dl.client_api.calls_counter.reset()

        # set env to dev
        if get_env_from_git_branch() != dl.client_api.environments[dl.client_api.environment]['alias']:
            context.dl.setenv(get_env_from_git_branch())

        # check token
        payload = None
        for i in range(10):
            try:
                payload = jwt.decode(context.dl.token(), algorithms=['HS256'], verify=False)
                break
            except jwt.exceptions.DecodeError:
                time.sleep(np.random.rand())
                pass
        if payload['email'] not in ['oa-test-1@dataloop.ai', 'oa-test-2@dataloop.ai', 'oa-test-3@dataloop.ai']:
            assert False, 'Cannot run test on user: "{}". only test users'.format(payload['email'])

        # save to feature level
        context.feature.dataloop_feature_dl = context.dl


@behave.given('There is a project by the name of "{project_name}"')
def step_impl(context, project_name):
    if hasattr(context.feature, 'dataloop_feature_project'):
        context.project = context.feature.dataloop_feature_project
    else:
        num = random.randint(10000, 100000)
        project_name = 'test_{}_{}'.format(str(num), project_name)
        context.project = context.dl.projects.create(project_name=project_name)
        context.feature.dataloop_feature_project = context.project
        time.sleep(5)
    context.dataset_count = 0

    if 'bot.create' in context.feature.tags:
        if hasattr(context.feature, 'bot_user'):
            context.bot_user = context.feature.bot_user
        else:
            bot_name = 'test_bot_{}'.format(random.randrange(1000, 10000))
            context.bot = context.project.bots.create(name=bot_name)
            context.feature.bot = context.bot
            context.bot_user = context.bot.email
            context.feature.bot_user = context.bot_user

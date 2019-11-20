import dtlpy as dl
import logging
logger = logging.getLogger(name=__name__)


class PluginRunner(dl.BasePluginRunner):
    """
    Plugin runner class

    """
    def __init__(self, **kwargs):
        """
        Init plugin attributes here
        
        :param kwargs: config params
        :return:
        """

    def run(self, progress=None):
        """
        Write your main plugin function here

        :param progress: Use this to update the progress of your plugin
        :return:
        """
        # these lines can be removed
        assert isinstance(progress, dl.Progress)
        progress.update(status='inProgress', progress=0)


if __name__ == "__main__":
    """
    Run this main to locally debug your plugin
    """
    dl.plugins.test_local_plugin()
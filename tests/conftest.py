import os
import sys

# ensure repo-local src wins even without editable install (clean-room runs)
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# load the agent_eval pytest plugin safely so benchmarks run from a clean
# clone without an editable install, while avoiding double-registration conflicts
def pytest_configure(config):
    if not config.pluginmanager.has_plugin("agent_eval") and not config.pluginmanager.has_plugin("agent_eval_harness.pytest_plugin"):
        import agent_eval_harness.pytest_plugin as plugin
        config.pluginmanager.register(plugin, name="agent_eval")


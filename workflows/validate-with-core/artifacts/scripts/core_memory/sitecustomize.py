"""Make CORE size its memory use to the container, not the host.

CORE v1.0.0 sizes its in-memory caches from psutil.virtual_memory().available
(25 % for results, 50 % for datasets, both held in its cache-manager process)
and picks Dask over pandas the same way. Inside a container psutil reports the
host's memory, so on a large host the caches grow past the container's limit
and the kernel kills a CORE process; the pool then waits forever for the lost
task. run_core.py puts this directory on PYTHONPATH and sets
CORE_MEMORY_BUDGET_BYTES; Python imports sitecustomize at start-up in every
CORE process, so each one sees that budget as its available memory.
"""

import os

budget_text = os.environ.get("CORE_MEMORY_BUDGET_BYTES", "")

if budget_text.isdigit() is True:
    import psutil

    budget = int(budget_text)
    host_virtual_memory = psutil.virtual_memory

    def container_virtual_memory():
        actual = host_virtual_memory()
        return actual._replace(total=min(actual.total, budget), available=min(actual.available, budget))

    psutil.virtual_memory = container_virtual_memory

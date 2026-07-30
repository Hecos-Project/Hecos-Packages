from hecos.modules.global_backup.core_logic.api import register_routes as init_backup_api
from hecos.modules.global_backup.core_logic.routes_modules import register_module_backup_routes
from hecos.modules.global_backup.core_logic import scheduler as backup_scheduler
from hecos.core.logging import logger

def init_plugin_routes(app, cfg_mgr=None, hecos_root=None, log=None):
    try:
        init_backup_api(app)
        logger.info("[HPM:GlobalBackup] Core API loaded.")
    except Exception as e:
        logger.warning(f"[HPM:GlobalBackup] Core API could not load: {e}")

    try:
        register_module_backup_routes(app)
        logger.info("[HPM:GlobalBackup] Module routes loaded.")
    except Exception as e:
        logger.warning(f"[HPM:GlobalBackup] Module routes could not load: {e}")

    try:
        backup_scheduler.start(app)
        logger.info("[HPM:GlobalBackup] Scheduler started.")
    except Exception as e:
        logger.warning(f"[HPM:GlobalBackup] Scheduler start error: {e}")


from enum import Enum


class SystemEvent(Enum):
    """
    Lista degli eventi di sistema che possono innescare una notifica.
    Il valore (str) deve combaciare con le chiavi del file notifications.yaml.
    """
    SYSTEM_BOOT        = "system_boot"
    SYSTEM_SHUTDOWN    = "system_shutdown"
    SYSTEM_ERROR       = "system_error"

    FLOW_STARTED       = "flow_started"
    FLOW_COMPLETED     = "flow_completed"
    FLOW_FAILED        = "flow_failed"

    PACKAGE_INSTALLED  = "package_installed"
    PACKAGE_UPDATED    = "package_updated"
    PACKAGE_REMOVED    = "package_removed"

    SECURITY_LOGIN_FAILED = "security_login_failed"
    SECURITY_NEW_DEVICE   = "security_new_device"

    # Evento generico usato per notifiche di test
    CUSTOM = "custom"

def classFactory(iface):
    from .yd_plugin import yd_iNaturalistImportPlugin
    return yd_iNaturalistImportPlugin(iface)
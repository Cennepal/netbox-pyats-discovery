# What now?
It's documented in german so either you know the language or you figure it out on your own. Basically implements following stuffs:
- VLAN scanning and updates to netbox
- Device creation from pyATS testbed with detailed device information
- Neighbouring device recognition and creation via cdp
- Device type, role and platform auto creation
- Automatic interface recognition and creation
- Automatic cable creation, again via cdp

# Why do I need this?
Again, I'm not selling crack. So how should I know?

# Nom Nom, give me dependencies!
Fine:
- pyats[full]
- pynetbox
- urllib3

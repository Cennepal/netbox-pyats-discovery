# Pynetbox ist für die Kommunikation mit der Netbox API zuständig
# Genie/pyATS ist für die Kommunikation mit den Geräten zuständig
# Urllib3 wird benötigt, um die HTTP Warnung auszuschalten
# Re wird benötigt, um die CDP Daten zu parsen
# ipaddress wird benötigt, um die IP Adressen zu parsen
# Random wird benötigt, um zufällige Farben für die Geräte Rollen zu wählen
from genie.testbed import load
import pynetbox, urllib3, re, random, os, logging
from ipaddress import ip_network
from dotenv import load_dotenv

# Umgebung Variablen irgendwie laden
if os.path.exists(".env"):
        load_dotenv(".env")
        pass
elif os.getenv("NETBOX_URL") == None:
        exit()

# Logging level ab DEBUG
LOG_LEVEL = os.getenv("LOG_LEVEL").upper()
logging.basicConfig(level=LOG_LEVEL, format="[{asctime}]-[{levelname}]: {message}", style="{", datefmt="%Y-%m-%d %H:%M:%S")

# Environment Variablen laden
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
SWITCH_USER = os.getenv("SWITCH_USER")
SWITCH_PASS = os.getenv("SWITCH_PASS")
logging.debug("Environment variables loaded:")
logging.debug(f"NETBOX_URL: {NETBOX_URL}")
logging.debug(f"NETBOX_TOKEN: {NETBOX_TOKEN}")
logging.debug(f"SWITCH_USER: {SWITCH_USER}")
logging.debug(f"SWITCH_PASS: {SWITCH_PASS}")

logging.info("Connecting to Netbox")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) # HTTP Warnung ausmachen
nb = pynetbox.api(url=NETBOX_URL, token=NETBOX_TOKEN) # Netbox API Verbindung
nb.http_session.verify = False # Keine Zertifikate checken

# ---- Funktion um Testbed zu erstellen ----
def MakeTestbed():
        # Unser Default testbed mit Zugangsdaten
        tb = {
                "testbed": {
                        "name": "NetboxTestbed",
                        "credentials": {
                                "default": {
                                        "username": SWITCH_USER,
                                        "password": SWITCH_PASS
                                }
                        }
                },
                "devices": {}
        }

        logging.info("Getting devices with role 'switch' from Netbox")
        switch_role_id = nb.dcim.device_roles.get(slug='switch').id
        nb_switches = nb.dcim.devices.filter(role_id=switch_role_id)
        logging.info(f"Found {len(nb_switches)} devices with role 'switch'. Adding them to the testbed")
        for switch in nb_switches:
                # Switche unter devices in das Testbed einfügen
                primary_ip = switch.primary_ip4.address.split('/')[0] if switch.primary_ip4 else '0.0.0.0'
                os = switch.custom_fields['OS'].lower()
                os = os.replace("-", "")
                tb["devices"][switch.name] = {
                        "type": "switch",
                        "os": os,
                        "connections": {
                                "cli": {
                                        "protocol": "ssh",
                                        "ip": primary_ip
                                }
                        }
                }

        logging.debug(f"TESTBED:\n {tb}")
        return tb

# ---- Funktion um Site ID zu setzen ----
def setSite(prefix_nb, prefix_str):
        # Wenn Prefix existiert, dann Site ID setzen, ansonsten Default Site ID setzen
        if prefix_nb != None:
                if prefix_nb.site != None:
                        logging.info(f"Site found for Prefix {prefix_str} with ID {prefix_nb.site.id} and Name {prefix_nb.site.name}, setting Site ID.")
                        st = prefix_nb.site.id
                        return st
                else:
                        logging.info(f"Site not found for Prefix {prefix_str}, setting default Site ID 5 with Name 'Unknown'")
                        st = 5
                        return st
        else:
                logging.info(f"Prefix {prefix_str} not found, setting default Site ID 5 with Name 'Unknown'")
                st = 5
                return st

# ---- Funktion um Interface Typen zu sortieren ----
def sortInterface(interface,mode):
        # Muss zwei modes erstellen, da bei CDP Nachbarn nur die Interface Namen genutzt werden kann um den Spec zu bestimmen
        if mode == "device":
                match interface:
                        case "10/100/1000BaseTX":
                                return "1000base-tx"
                        case "1000BaseSX SFP":
                                return "1000base-x-sfp"
                        case "10/100BaseTX":
                                return "100base-tx"
                        case "SFP-10GBase-LR":
                                return "10gbase-x-sfpp"
                        case "SFP-10GBase-SR":
                                return "10gbase-x-sfpp"
                        case "SFP-10GBase-LRM":
                                return "10gbase-x-sfpp"
                        case "SFP-10GBase-CX1":
                                return "10gbase-x-sfpp"
                        case "100/1000/2.5G/5G/10GBaseTX":
                                return "10gbase-t"
                        case "unknown":
                                return "other"
                        case "Not Present":
                                return "other"
                        case _:
                                return "virtual"
        elif mode == "cdp":
                if "TenGigabitEthernet" in interface:
                        return "10gbase-t"
                elif "FastEthernet" in interface:
                        return "100base-tx"
                elif "GigabitEthernet" in interface:
                        return "1000base-tx"
                elif "mgmt" in interface:
                        return "other"
                else:
                        return "virtual"
        else:
                return "other"

# ---- Funktion um Farben für Geräte Rollen zu wählen ----
def pickColor():
        used_colors = []
        colors = [
        'FF6F61',  # Light Coral
        'FFB07C',  # Peach
        'FFD700',  # Gold
        'FFEF96',  # Pale Yellow
        'BEEB9F',  # Light Green
        'A7D8AD',  # Seafoam Green
        '77D8D8',  # Light Blue
        'AEC6CF',  # Light Grayish Blue
        'B39EB5',  # Lavender
        'D7B9D5',  # Light Lilac
        'FFC3A0',  # Light Salmon
        'FFABAB',  # Light Pink
        'FFC3A0',  # Light Salmon
        'FF677D',  # Light Red
        'FFD3B5',  # Light Apricot
        'FFD3B5',  # Light Apricot
        ]
        available_colors = [color for color in colors if color not in used_colors]
        if not available_colors: # muss gemacht werden, seed ändern hat nicht funktioniert
                used_colors = []
                available_colors = colors
        color = random.choice(colors).lower() # Netbox entwickler finden sich schlau kleinschreibung zu enforcen (ノ#-_-)ノ ミ┴┴
        used_colors.append(color)
        return color

# ---- Funktion um halbverbundene Kabel zu entfernen ----
def removeLooseCables():
        logging.info(f"Removing all loose cables...")
        # Schauen ob es Kabel mit unvollständigen Terminierungen gibt und diese löschen
        cables = nb.dcim.cables.all()
        for cable in cables:
                if not cable.a_terminations or not cable.b_terminations:
                        logging.info(f"Removing cable with ID {cable.id} because it has loose terminations")
                        cable.delete()

# ---- Funktion um Inventory zu erstellen ----
def createInventory(invpar,hostname,host,stacked):
        logging.info(f"Adding inventory of {hostname}...")
        # Liste für Seriennummern der Sachen in Netbox machen
        netbox_sns = []
        switch_sns = []

        # Seriennummern der Inventory Items in Netbox holen
        inventory_items = nb.dcim.inventory_items.filter(device_id=host.id)
        for item in inventory_items:
            if item.serial:
                netbox_sns.append(item.serial)

        # Seriennummern der Module im Switch holen
        if tb.devices[hostname].os == 'ios':
                for slot, slot_data in invpar['slot'].items():
                        for rp, rp_data in slot_data['rp'].items():
                                inv_serial = rp_data['sn']
                                switch_sns.append(inv_serial)
        elif tb.devices[hostname].os == 'iosxe':
                for name, data in invpar['name'].items():
                        inv_serial = data['sn']
                        switch_sns.append(inv_serial)

        # Seriennummern die in Netbox sind, aber nicht im Switch sind löschen
        serials_to_delete = set(netbox_sns) - set(switch_sns)
        for serial in serials_to_delete:
                inventory_item = nb.dcim.inventory_items.get(serial=serial)
                if inventory_item:
                        logging.info(f"Deleting inventory item with Serial {serial} as it is not in switch_sns")
                        inventory_item.delete()
        # Für jedes Inventory Item
        # Unterschiedliche Methoden für IOS und IOSXE, da die Daten anders strukturiert sind
        if tb.devices[hostname].os == 'ios':
                for slot, slot_data in invpar['slot'].items():
                        for rp, rp_data in slot_data['rp'].items():
                                inv_name = f"{hostname}-{rp_data['name']}"
                                inv_serial = rp_data['sn']
                                inv_model = rp_data['pid'] if 'pid' in rp_data else rp_data['description']

                                # SFP Module mit Bays erstellen
                                if 'subslot' in rp_data:
                                        for subslot_name, subslot_data in rp_data['subslot'].items():
                                                for sfp_name, sfp_data in subslot_data.items():
                                                        # Erstelle 'name' als Modulebay und 'pid' als SFP Module
                                                        if not nb.dcim.module_bays.filter(name=subslot_name, device_id=host.id):
                                                                logging.info(f"Module Bay {subslot_name} not in Netbox, creating it now")
                                                                m_bay = nb.dcim.module_bays.create(name=subslot_name, device=host.id)
                                                        else:
                                                                logging.info(f"Module Bay {subslot_name} already in Netbox")
                                                                m_bay = nb.dcim.module_bays.get(name=subslot_name, device_id=host.id)

                                                        # Erstelle Module Type wenn nicht vorhanden
                                                        if not nb.dcim.module_types.filter(model=sfp_data['pid']):
                                                                logging.info(f"SFP Module Type {sfp_data['pid']} not in Netbox, creating it now")
                                                                m_type = nb.dcim.module_types.create(model=sfp_data['pid'], manufacturer=2)
                                                        else:
                                                                logging.info(f"SFP Module Type {sfp_data['pid']} already in Netbox")
                                                                m_type = nb.dcim.module_types.get(model=sfp_data['pid'])

                                                        # Erstelle SFP Module wenn nicht vorhanden
                                                        if not nb.dcim.modules.filter(module_bay_id=m_bay.id, device_id=host.id):
                                                                logging.info(f"SFP Module {sfp_data['pid']} with serial {sfp_data['sn']} not in Netbox, creating it now")
                                                                nb.dcim.modules.create(serial=sfp_data['sn'], module_type=m_type.id, device=host.id, module_bay=m_bay.id)

                                                        # Wenn SFP Module in Netbox existiert, dann Daten updaten
                                                        elif nb.dcim.modules.filter(module_bay_id=m_bay.id, device_id=host.id):
                                                                logging.info(f"SFP Module {sfp_data['pid']} already in Netbox - updating information")
                                                                rset = nb.dcim.modules.get(module_bay_id=m_bay.id, device_id=host.id)
                                                                rset.serial = sfp_data['sn']
                                                                rset.module_type = m_type.id
                                                                rset.save()
                                # Erstelle inventory item nicht wenn das Gerät nicht gestackt ist
                                if not stacked and inv_name == f"{hostname}-1":
                                        continue
                                # Wenn Inventory Item in Netbox nicht existiert, dann erstellen
                                elif not nb.dcim.inventory_items.filter(serial=inv_serial):
                                        logging.info(f"Inventory Item {inv_name} with Serial {inv_serial} not in Netbox, creating it now")
                                        nb.dcim.inventory_items.create(device=host.id, name=inv_name, manufacturer=1, serial=inv_serial, part_id=inv_model)
                                else:
                                        logging.info(f"Inventory Item {inv_name} with Serial {inv_serial} already in Netbox")

        elif tb.devices[hostname].os == 'iosxe':
                for name, data in invpar['name'].items():
                        inv_name = f"{hostname}-{name}"
                        inv_serial = data['sn']
                        inv_model = data['pid'] if 'pid' in data else data['description']
                        # Schauen ob SFP im Inventory
                        if not "SFP" in inv_model:
                                        # Non-Stacked Geräte nicht im Inventory erstellen
                                        if not stacked and inv_name == f"{hostname}-1":
                                                        continue
                                        # Erstellen wenn nicht vorhanden
                                        elif not nb.dcim.inventory_items.filter(serial=inv_serial):
                                                        logging.info(f"Inventory Item {inv_name} with Serial {inv_serial} not in Netbox, creating it now")
                                                        nb.dcim.inventory_items.create(device=host.id, name=inv_name, manufacturer=1, serial=inv_serial, part_id=inv_model)
                                        else:
                                                        logging.info(f"Inventory Item {inv_name} with Serial {inv_serial} already in Netbox")
                        else:
                                        # Erstelle 'name' als Modulebay und 'pid' als SFP Module
                                        if not nb.dcim.module_bays.filter(name=name, device_id=host.id):
                                                        logging.info(f"Module Bay {name} not in Netbox, creating it now")
                                                        m_bay = nb.dcim.module_bays.create(name=name, device=host.id)
                                        else:
                                                        logging.info(f"Module Bay {name} already in Netbox")
                                                        m_bay = nb.dcim.module_bays.get(name=name, device_id=host.id)

                                        # Erstelle Module Type wenn nicht vorhanden
                                        if not nb.dcim.module_types.filter(model=inv_model):
                                                        logging.info(f"SFP Module Type {inv_model} not in Netbox, creating it now")
                                                        m_type = nb.dcim.module_types.create(model=inv_model, manufacturer=2)
                                        else:
                                                        logging.info(f"SFP Module Type {inv_model} already in Netbox")
                                                        m_type = nb.dcim.module_types.get(model=inv_model)

                                        # Erstelle SFP Module wenn nicht vorhanden
                                        if not nb.dcim.modules.filter(module_bay_id=m_bay.id, device_id=host.id):
                                                        logging.info(f"SFP Module {inv_model} with serial {inv_serial} not in Netbox, creating it now")
                                                        nb.dcim.modules.create(serial=inv_serial, module_type=m_type.id, device=host.id, module_bay=m_bay.id)

                                        # Wenn SFP Module in Netbox existiert, dann Daten updaten
                                        elif nb.dcim.modules.filter(module_bay_id=m_bay.id, device_id=host.id):
                                                        logging.info(f"SFP Module {inv_model} with serial {inv_serial} already in Netbox - updating information")
                                                        rset = nb.dcim.modules.get(module_bay_id=m_bay.id, device_id=host.id)
                                                        rset.serial = inv_serial
                                                        rset.module_type = m_type.id
                                                        rset.save()


# ---- Cisco Geräte entdeckung ----
def discoverCiscoDevice(nb,tb,device_name):

        # ---- Verbindung zum Gerät aufbauen und Daten sammeln ----
        logging.info(f"Connecting to {device_name}...")
        dev = tb.devices[device_name]
        try:
            dev.connect(goto_enable=False,
                        log_stdout=False,
                        init_exec_commands=[],
                        init_config_commands=[])
        except Exception as e:
                logging.error(f"Error connecting to {device_name}. Can the host reach it? Are the credentials correct?")
                logging.error(f"Exception: {e}")
                return

        # ---- Befehle auf dem Gerät ausführen und Daten parsen ----
        logging.info(f"Executing commands and parsing data...")
        verraw = dev.execute('show version')
        vlanraw = dev.execute('show vlan')
        intraw = dev.execute('show interfaces status')
        cdpraw = dev.execute('show cdp neighbors detail')
        # OID ist näher an das IOS 'show inventory' dran als IOSXE 'show inventory'
        if tb.devices[device_name].os == 'ios':
                logging.info(f"Device {device_name} is running IOS, using 'show inventory'")
                invraw = dev.execute('show inventory')
        elif tb.devices[device_name].os == 'iosxe':
                logging.info(f"Device {device_name} is running IOSXE, using 'show inventory OID'")
                invraw = dev.execute('show inventory OID')
        # Nicht jeder switch hat dieses Command, deshalb try/except
        try:
                swraw = dev.execute('show switch')
                sw_errored = False
        except Exception as e:
                logging.error(f"Error executing 'show switch' on {device_name}, skipping stack creation")
                logging.error(f"Exception: {e}")
                sw_errored = True

        logging.info("Disconnecting from device...")
        dev.disconnect()

        # ---- Raw und Parsed Variablen für Debug Zwecke ----
        verpar = dev.parse('show version', output=verraw)
        vlanpar = dev.parse('show vlan', output=vlanraw)
        intpar = dev.parse('show interfaces status', output=intraw)
        cdppar = dev.parse('show cdp neighbors detail', output=cdpraw)
        if tb.devices[device_name].os == 'ios':
                invpar = dev.parse('show inventory', output=invraw)
        elif tb.devices[device_name].os == 'iosxe':
                invpar = dev.parse('show inventory OID', output=invraw)
        if not sw_errored:
                swpar = dev.parse('show switch', output=swraw)

        # ---- Daten aus 'show version' extrahieren ----
        hostname = verpar['version']['hostname']
        os = verpar['version']['os']
        os_ver = verpar['version']['version']
        serial_num = verpar['version']['chassis_sn']
        platform = verpar['version']['platform']
        platform_slug = platform.replace(" ", "-")
        chassis = verpar['version']['chassis']

        # ---- VLANs in Netbox erstellen und ergänzen ----
        logging.info(f"Checking VLANs...")
        for vlan in vlanpar['vlans']:
                vlan_name = vlanpar['vlans'][vlan]['name']
                vlan_id = vlanpar['vlans'][vlan]['vlan_id']
                existing_vlan = nb.ipam.vlans.get(vid=vlan_id)
                # Wenn VLAN existiert, aber Name nicht übereinstimmt, dann updaten (Daten werden vom Gerät übernommen)
                if existing_vlan:
                        if existing_vlan.name != vlan_name:
                                logging.info(f"Name of VLAN {vlan_id} is outdated, updating to {vlan_name}")
                                existing_vlan.name = vlan_name
                                existing_vlan.full_clean()
                                existing_vlan.save()
                else:
                        # Wenn VLAN nicht existiert, dann erstellen
                        logging.info(f"Creating VLAN {vlan_name} with ID {vlan_id}")
                        nb.ipam.vlans.create(name=vlan_name, vid=vlan_id)

        # ---- Device in Netbox erstellen und ergänzen ----
        logging.info(f"Checking Device {hostname}...")
        # Schauen ob Device Type und Platform in Netbox existieren
        device_type_chk = nb.dcim.device_types.get(slug=chassis)
        platform_chk = nb.dcim.platforms.get(slug=platform_slug)

        # IP Adresse des Gerätes aus Verbindung holen
        ip_address_str = str(dev.connections['cli'].ip)+"/24"

        # Schauen ob IP Adresse in Netbox existiert, wenn nicht, dann erstellen
        if not nb.ipam.ip_addresses.filter(address=ip_address_str):
                logging.info(f"IP Address not in Netbox, creating {ip_address_str}")
                nb.ipam.ip_addresses.create(address=ip_address_str, status='online')

        # Prefix des Gerätes aus IP Adresse holen und schauen ob Prefix in Netbox existiert
        prefix_str = str(ip_network(ip_address_str, strict=False).supernet().network_address)+"/24"
        logging.info(f"Checking Prefix {prefix_str}")
        prefix_nb = nb.ipam.prefixes.get(prefix=prefix_str)
        # Existierende Site config nicht überschreiben
        if nb.dcim.devices.filter(name=hostname):
                st = nb.dcim.devices.get(name=hostname).site.id
        else:
                st = setSite(prefix_nb, prefix_str)

        # Schauen ob Platform in Netbox existiert, wenn nicht, dann erstellen
        if not platform_chk:
                logging.info(f"Platform not in Netbox, creating {platform}")
                nb.dcim.platforms.create(name=platform, slug=platform_slug)
                tmp = nb.dcim.platforms.get(slug=platform_slug)
                pf = tmp.id
        else:
                logging.info(f"Platform {platform} already in Netbox")
                tmp = nb.dcim.platforms.get(slug=platform_slug)
                pf = tmp.id

        # Dasselbe für Device Type
        if not device_type_chk:
                logging.info(f"Device Type not in Netbox, creating {chassis}")
                nb.dcim.device_types.create(model=chassis, slug=chassis, manufacturer=1)
                tmp = nb.dcim.device_types.get(slug=chassis)
                dt = tmp.id
        else:
                logging.info(f"Device Type {chassis} already in Netbox")
                tmp = nb.dcim.device_types.get(slug=chassis)
                dt = tmp.id

        # Checken ob es sich um ein Stack handelt (in swpar chechken)
        if not sw_errored:
                slot_count = len(swpar["switch"]["stack"])
        else:
                slot_count = 1

        if slot_count > 1:
                logging.info(f"Stacked Device detected, setting Serial Number to None")
                serial_num = ''
                stacked = True
        else:
                # Stacked setzen, damit Standalone Switche mit dem 'show switch' Command nicht als gestackt erkannt werden
                stacked = False
                logging.info(f"Device is not stacked, setting Serial Number to {serial_num}")

        # Objekt für das Gerät aus Netbox holen
        host = nb.dcim.devices.get(name=hostname)
        # Wenn Gerät in Netbox existiert, dann Daten updaten, ansonsten erstellen
        if host:
                logging.info(f"Device {hostname} is already in netbox - updating information")
                host.device_type = dt
                host.platform = pf
                host.serial = serial_num
                host.site = st
                host.custom_fields={'OS':os, 'Version':os_ver} # Bei verschachtelten Fields muss dass so gemacht werden
                host.save()
        else:
                logging.info(f"Device {hostname} is not in netbox, creating it now")
                nb.dcim.devices.create(name=hostname, device_type=dt, platform=pf, serial=serial_num, role=1, status='active', site=st, custom_fields={'OS':os,'Version':os_ver}, primary_ip4=None, primary_ip6=None)
                host = nb.dcim.devices.get(name=hostname) # Host Objekt neu holen, da es in diesem Fall vorher nicht existiert hat
                logging.info(f"Device {hostname} created with ID {host.id} created")

        # ---- Interfaces in Netbox erstellen und ergänzen ----
        logging.info(f"Adding interfaces to {hostname}")
        # Für jede Interface im Interface Dictionary
        for interface_name, interface_data in intpar['interfaces'].items():
                # Schauen ob das Interface überhaupt einen Typ hat, wenn nicht dann None setzen
                if 'type' not in interface_data:
                        chk_int_type = None
                else:
                        chk_int_type = interface_data['type']

                netbox_type = sortInterface(chk_int_type,"device")

                # Schauen ob das Interface einen Namen hat, wenn nicht dann 'N/A' setzen
                if 'name' in interface_data:
                        desc = interface_data['name']
                else:
                        desc = 'N/A'

                # Wenn Interface in Netbox existiert, dann Daten updaten, ansonsten erstellen
                interface = nb.dcim.interfaces.get(name=interface_name, device_id=host.id)
                if interface != None:
                        logging.info(f"Interface {interface_name} already exists on Device {hostname} - updating information")
                        interface.label = interface_data['status']
                        interface.type = netbox_type
                        interface.description = desc
                        interface.save()
                        nb.dcim.interfaces.get(name=interface_name, device_id=host.id)
                else:
                        logging.info(f"Creating Interface {interface_name}")
                        nb.dcim.interfaces.create(type=netbox_type, name=interface_name, device=host.id, label=interface_data['status'], description=desc)

        # ---- CDP Nachbarn in Netbox erstellen und ergänzen ----
        logging.info(f"Checking CDP Neighbors for {hostname}...")
        removeLooseCables()
        # Für jeden CDP Nachbarn
        for index, device_info in cdppar['index'].items():
                # Daten aus CDP Nachbar extrahieren und korrekt formatieren
                cdp_device_id = device_info.get('device_id', 'N/A')
                cdp_device_id = cdp_device_id # .rstrip('.domain.ad') Wenn du eine AD Domäne im Namen von erkannten Geräten hast, dann kannst du das hier benutzen
                cdp_device_role = device_info.get('capabilities', 'N/A')
                cdp_device_role_slug = cdp_device_role.replace(' ', '_')
                cdp_device_type = device_info.get('platform', 'N/A').replace('cisco ', '')
                cdp_device_type_slug = cdp_device_type.replace(' ', '_')
                cdp_platform = re.sub('^WS-', '', cdp_device_type).split('-')[0]
                cdp_local_interface = device_info.get('local_interface', 'N/A')
                cdp_port_id = device_info.get('port_id', 'N/A')
                management_addresses = device_info.get('management_addresses', {})
                cdp_native_vlan = device_info.get('native_vlan', 'N/A')
                cdp_sw_ver = device_info.get('software_version', 'N/A')
                if management_addresses:
                        cdp_mgmt_ip = next(iter(management_addresses))

                # Wenn Platform in Netbox existiert, dann ID holen, ansonsten erstellen
                if not nb.dcim.platforms.filter(slug=cdp_platform):
                        logging.info(f"Platform {cdp_platform} not in Netbox, creating it now")
                        # Für namen mit Leerzeichen
                        cdp_platform = cdp_platform.replace(" ", "-")
                        nb.dcim.platforms.create(name=cdp_platform, slug=cdp_platform)
                        tmp = nb.dcim.platforms.get(slug=cdp_platform)
                        pf = tmp.id
                else:
                        logging.info(f"Platform {cdp_platform} already in Netbox")
                        tmp = nb.dcim.platforms.get(slug=cdp_platform)
                        pf = tmp.id

                # Hier dasselbe für Device Type
                if not nb.dcim.device_types.filter(slug=cdp_device_type_slug):
                        logging.info(f"Device Type {cdp_device_type} not in Netbox, creating it now")
                        nb.dcim.device_types.create(model=cdp_device_type, slug=cdp_device_type_slug, manufacturer=1)
                        tmp = nb.dcim.device_types.get(slug=cdp_device_type_slug)
                        dt = tmp.id
                else:
                        logging.info(f"Device Type {cdp_device_type} already in Netbox")
                        tmp = nb.dcim.device_types.get(slug=cdp_device_type_slug)
                        dt = tmp.id

                # Wenn IP Adresse des Nachbarn in Netbox nicht existiert, dann erstellen
                if not nb.ipam.ip_addresses.filter(address=cdp_mgmt_ip+"/24"):
                        logging.info(f"IP Address {cdp_mgmt_ip}/24 not in Netbox, creating it now")
                        nb.ipam.ip_addresses.create(address=cdp_mgmt_ip+"/24", status='online')
                else:
                        logging.info(f"IP Address {cdp_mgmt_ip}/24 already in Netbox")

                cdp_ipint = nb.ipam.ip_addresses.get(address=cdp_mgmt_ip+"/24")

                # 'Capabilities' als Device Role in Netbox erstellen wenn nicht vorhanden
                if not nb.dcim.device_roles.filter(slug=cdp_device_role_slug.lower()):
                        logging.info(f"Role {cdp_device_role} not in Netbox, creating it now")
                        nb.dcim.device_roles.create(name=cdp_device_role, slug=cdp_device_role_slug.lower(), color=pickColor())
                        tmp = nb.dcim.device_roles.get(slug=cdp_device_role_slug.lower())
                        rl = tmp.id

                # Wenn das Gerät "Switch" im ersten Wort hat, dann wird es die Switch Rolle bekommen
                if cdp_device_role_slug.lower().split('_')[0] == 'switch':
                        logging.info(f"Device Role {cdp_device_role} is a switch, setting to switch")
                        rl = nb.dcim.device_roles.get(slug='switch').id
                else:
                        logging.info(f"Device Role {cdp_device_role} is not a switch, setting to {cdp_device_role_slug}")
                        tmp = nb.dcim.device_roles.get(slug=cdp_device_role_slug.lower())
                        rl = tmp.id

                # OS des Nachbarn aus Software Version holen
                if "IOS-XE" in cdp_sw_ver:
                        cdp_os = "IOS-XE"
                        logging.info(f"OS of {cdp_device_id} is {cdp_os}")
                elif "NX-OS" in cdp_sw_ver:
                        cdp_os = "NX-OS"
                        logging.info(f"OS of {cdp_device_id} is {cdp_os}")
                elif "IOS" in cdp_sw_ver:
                        cdp_os = "IOS"
                        logging.info(f"OS of {cdp_device_id} is {cdp_os}")
                else:
                        cdp_os = "N/A"
                        logging.info(f"OS of {cdp_device_id} could not be determined. Setting to N/A")

                # Prefix des Nachbarn aus IP Adresse holen und schauen ob Prefix in Netbox existiert
                prefix_str = str(ip_network(cdp_mgmt_ip+"/24", strict=False).supernet().network_address)+"/24"
                logging.info(f"Checking Prefix {prefix_str}")
                prefix_nb = nb.ipam.prefixes.get(prefix=prefix_str)
                if nb.dcim.devices.filter(name=cdp_device_id):
                        st = nb.dcim.devices.get(name=cdp_device_id).site.id
                else:
                        st = setSite(prefix_nb, prefix_str)

                # Wenn Device in Netbox nicht existiert, dann erstellen, ansonsten Daten updaten
                if not nb.dcim.devices.filter(name=cdp_device_id):
                        logging.info(f"Device {cdp_device_id} not in Netbox, creating it now")
                        nb.dcim.devices.create(name=cdp_device_id, device_type=dt, platform=pf, role=rl, status='active', site=st, custom_fields={'OS':cdp_os}, primary_ip4=None, primary_ip6=None)
                else:
                        logging.info(f"Device {cdp_device_id} already in Netbox - updating information")
                        cdp_device_host = nb.dcim.devices.get(name=cdp_device_id)
                        cdp_device_host.device_type = dt
                        cdp_device_host.platform = pf
                        cdp_device_host.role = rl
                        cdp_device_host.site = st
                        cdp_device_host.custom_fields={'OS':cdp_os}
                        cdp_device_host.save()

                # Verbundenes Interface zum Nachbarn erstellen, wenn nicht vorhanden
                if not nb.dcim.interfaces.filter(name=cdp_local_interface, device_id=host.id):
                        netbox_type = sortInterface(cdp_local_interface,"cdp")

                        logging.info(f"Interface {cdp_local_interface} not in Netbox, creating it now")
                        nb.dcim.interfaces.create(name=cdp_local_interface, device=host.id, type=netbox_type, enabled=True)
                else:
                        logging.info(f"Interface {cdp_local_interface} already in Netbox")

                # Wenn Interface des Nachbarn in Netbox nicht existiert, dann erstellen
                if not nb.dcim.interfaces.filter(name=cdp_port_id, device=cdp_device_id):
                        netbox_type = sortInterface(cdp_port_id, "cdp")

                        logging.info(f"Interface {cdp_port_id} not in Netbox, creating it now")
                        cdp_device_host = nb.dcim.devices.get(name=cdp_device_id)
                        nb.dcim.interfaces.create(name=cdp_port_id, device=cdp_device_host.id, type=netbox_type, enabled=True)

                        cdp_port_id_int = nb.dcim.interfaces.get(name=cdp_port_id, device_id=cdp_device_host.id)
                        cdp_local_interface_int = nb.dcim.interfaces.get(name=cdp_local_interface, device_id=host.id)

                        # IP Adresse des Nachbarn zuweisen, wenn nicht vorhanden
                        if cdp_ipint.assigned_object_id:
                                logging.info(f"IP Address {cdp_mgmt_ip}/24 already assigned to {cdp_ipint.assigned_object_type} with ID {cdp_ipint.assigned_object_id}")
                        elif not cdp_native_vlan:
                                logging.info(f"Assigning IP Address {cdp_mgmt_ip}/24 to Interface {cdp_port_id}")
                                cdp_ipint.assigned_object_id = cdp_port_id_int.id
                                cdp_ipint.assigned_object_type = "dcim.interface"
                                cdp_ipint.save()

                                logging.info(f"Setting Primary IP Address {cdp_mgmt_ip}/24 on Device {cdp_device_id}")
                                cdp_ipset = nb.dcim.devices.get(name=cdp_device_id)
                                cdp_ipset.primary_ip4 = cdp_ipint.id
                                cdp_ipset.save()
                        # Wenn Native VLAN vorhanden, dann VLAN Interface erstellen und IP Adresse zuweisen
                        else:
                                logging.info(f"Assigning IP Address {cdp_mgmt_ip}/24 to Vlan{cdp_native_vlan}")
                                vname = f"Vlan{cdp_native_vlan}"
                                nb.dcim.interfaces.create(name=vname, device=cdp_device_host.id, type=netbox_type, enabled=True)
                                cdp_vlan_int = nb.dcim.interfaces.get(name=vname, device_id=cdp_device_host.id)
                                cdp_ipint.assigned_object_id = cdp_vlan_int.id
                                cdp_ipint.assigned_object_type = "dcim.interface"
                                cdp_ipint.save()

                                logging.info(f"Setting Primary IP Address {cdp_mgmt_ip}/24 on Device {cdp_device_id}")
                                cdp_ipset = nb.dcim.devices.get(name=cdp_device_id)
                                cdp_ipset.primary_ip4 = cdp_ipint.id
                                cdp_ipset.save()

                else:
                        logging.info(f"Interface {cdp_port_id} already in Netbox")

                # Kabel zwischen Interface und Port erstellen, wenn nicht vorhanden
                # Richtig komisch, dass die filter keys anders sind als die, die ich beim erstellen setze
                cdp_port_id_int = nb.dcim.interfaces.get(name=cdp_port_id, device_id=cdp_device_host.id)
                cdp_local_interface_int = nb.dcim.interfaces.get(name=cdp_local_interface, device_id=host.id)

                # Muss beide Richtungen checken, wenn beide Terminierungsobjekte Switche sind
                existing_cables = nb.dcim.cables.get(termination_a_id=cdp_local_interface_int.id, termination_b_id=cdp_port_id_int.id)
                existing_cables_b = nb.dcim.cables.get(termination_a_id=cdp_port_id_int.id, termination_b_id=cdp_local_interface_int.id)
                term = nb.dcim.cables.get(termination_b_id=cdp_port_id_int.id)
                term_b = nb.dcim.cables.get(termination_b_id=cdp_local_interface_int.id)
                if not existing_cables and not existing_cables_b:
                        # Die beiden Ifs sind um zu checken, ob die Terminierungen in Netbox noch die realität abbilden
                        if term != None:
                                logging.info(f"Cable exists between {cdp_local_interface} and {cdp_port_id}, updating terminations")
                                term.a_terminations = [{'object_type':'dcim.interface','object_id':cdp_local_interface_int.id}]
                                term.b_terminations = [{'object_type':'dcim.interface','object_id':cdp_port_id_int.id}]
                                term.save()
                        elif term_b != None:
                                logging.info(f"Cable exists between {cdp_local_interface} and {cdp_port_id}, updating terminations")
                                term_b.a_terminations = [{'object_type':'dcim.interface','object_id':cdp_port_id_int.id}]
                                term_b.b_terminations = [{'object_type':'dcim.interface','object_id':cdp_local_interface_int.id}]
                                term_b.save()
                        else:
                                logging.info(f"Creating Cable between {cdp_local_interface} and {cdp_port_id}")
                                try:
                                        nb.dcim.cables.create(a_terminations=[{'object_type':'dcim.interface','object_id':cdp_local_interface_int.id}], b_terminations=[{'object_type':'dcim.interface','object_id':cdp_port_id_int.id}], status='connected')
                                except pynetbox.core.query.RequestError as e:
                                        logging.error(f"Error creating cable between {cdp_local_interface} and {cdp_port_id}. This is most likely caused by a new interface type not found in sortInterface() and one of the terminations being set to 'Virtual'. Please add the new type to sortInterface() and try again.")
                                        logging.debug(f"Exception: {e}")

                else:
                        logging.info(f"Cable between {cdp_local_interface} and {cdp_port_id} already exists")
        # Inventory und Module in Netbox erstellen und ergänzen
        createInventory(invpar,hostname,host,stacked)
        logging.info(f"Finished processing {hostname}")

# Testbed erstellen und dann an Genie weitergeben
tb = MakeTestbed()
logging.info("Loading testbed into Genie")
tb = load(tb)

# ---- Parsing und Verarbeitung der Daten ----
for device_name,device in tb.devices.items():
        # Nur Cisco Geräte verarbeiten
        if 'ios' in device.os or 'iosxe' in device.os:
                discoverCiscoDevice(nb,tb,device_name)
# Pynetbox ist für die Kommunikation mit der Netbox API zuständig
# Genie/pyATS ist für die Kommunikation mit den Geräten zuständig
# Urllib3 wird benötigt, um die HTTP Warnung auszuschalten
# Re wird benötigt, um die CDP Daten zu parsen
# ipaddress wird benötigt, um die IP Adressen zu parsen
# Random wird benötigt, um zufällige Farben für die Geräte Rollen zu wählen
from genie.testbed import load
import pynetbox, urllib3, re, random
from ipaddress import ip_network



urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) # HTTP Warnung ausmachen
nb = pynetbox.api(url="<NEBTOX_URL>", token="<TOKEN>") # Netbox API Verbindung
nb.http_session.verify = False # Keine Zertifikate checken
tb = load('tb.yaml') # Testbed laden

# ---- Funktion um Site ID zu setzen ----
def setSite(prefix_nb, prefix_str):
        # Wenn Prefix existiert, dann Site ID setzen, ansonsten Default Site ID setzen
        if prefix_nb != None:
                if prefix_nb.site != None:
                        print(f"[+] Site found for Prefix {prefix_str} with ID {prefix_nb.site.id} and Name {prefix_nb.site.name}, setting Site ID.")
                        st = prefix_nb.site.id
                        return st
                else:
                        print(f"[+] Site not found for Prefix {prefix_str}, setting default Site ID 5 with Name 'Unknown'")
                        st = 5
                        return st
        else:
                print(f"[+] Prefix {prefix_str} not found, setting default Site ID 5 with Name 'Unknown'")
                st = 5
                return st

# ---- Funktion um Interface Typen zu sortieren ----
def sortInterface(interface):
        if 'Vlan' in interface:
                return 'virtual'
        elif 'FastEthernet' in interface:
                return '100base-tx'
        elif 'GigabitEthernet' in interface:
                return '1000base-t'
        elif 'TenGigabitEthernet' in interface:
                return '10gbase-t'
        else:
                return 'virtual'

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
        if not available_colors:
                used_colors = []
                available_colors = colors
        color = random.choice(colors).lower() # Netbox entwickler finden sich schlau kleinschreibung zu enforcen (ノ#-_-)ノ ミ┴┴
        used_colors.append(color)
        return color

# ---- Funktion um halbverbundene Kabel zu entfernen ----
def removeLooseCables():
        print(f"[*] Removing all loose cables...")
        # Check if there are any cables with only one termination or none at all
        cables = nb.dcim.cables.all()
        for cable in cables:
                if not cable.a_terminations or not cable.b_terminations:
                        print(f"[-] Removing cable with ID {cable.id} because it has loose terminations")
                        cable.delete()

# ---- Cisco Geräte entdeckung ----
def discoverCiscoDevice(nb,tb,device_name):

        # ---- Verbindung zum Gerät aufbauen und Daten sammeln ----
        print(f"[*] Connecting to {device_name}...")
        dev = tb.devices[device_name]
        dev.connect(goto_enable=False,
        log_stdout=False,
        init_exec_commands=[],
        init_config_commands=[])

        # ---- Befehle auf dem Gerät ausführen und Daten parsen ----
        print(f"[*] Executing commands and parsing data...")
        verraw = dev.execute('show version')
        vlanraw = dev.execute('show vlan')
        intraw = dev.execute('show ip interface')
        cdpraw = dev.execute('show cdp neighbors detail')

        # ---- Raw und Parsed Variablen für Debug Zwecke ----
        verpar = dev.parse('show version', output=verraw)
        vlanpar = dev.parse('show vlan', output=vlanraw)
        intpar = dev.parse('show ip interface', output=intraw)
        cdppar = dev.parse('show cdp neighbors detail', output=cdpraw)

        dev.disconnect()

        # ---- Daten aus den Befehlen extrahieren ----
        hostname = verpar['version']['hostname']
        os = verpar['version']['os']
        os_ver = verpar['version']['version']
        serial_num = verpar['version']['chassis_sn']
        platform = verpar['version']['platform']
        chassis = verpar['version']['chassis']

        # ---- VLANs in Netbox erstellen und ergänzen ----
        print(f"[*] Checking VLANs...")
        for vlan in vlanpar['vlans']:
                vlan_name = vlanpar['vlans'][vlan]['name']
                vlan_id = vlanpar['vlans'][vlan]['vlan_id']
                existing_vlan = nb.ipam.vlans.get(vid=vlan_id)
                # Wenn VLAN existiert, aber Name nicht übereinstimmt, dann updaten (Daten werden vom Gerät übernommen)
                if existing_vlan:
                        if existing_vlan.name != vlan_name:
                                print(f"[*] Name of VLAN {vlan_id} is outdated, updating to {vlan_name}")
                                existing_vlan.name = vlan_name
                                existing_vlan.save()
                else:
                        # Wenn VLAN nicht existiert, dann erstellen
                        print(f"[+] Creating VLAN {vlan_name} with ID {vlan_id}")
                        nb.ipam.vlans.create(name=vlan_name, vid=vlan_id)

        # ---- Device in Netbox erstellen und ergänzen ----
        print(f"[*] Checking Device {hostname}...")
        # Schauen ob Device Type und Platform in Netbox existieren
        device_type_chk = nb.dcim.device_types.get(slug=chassis)
        platform_chk = nb.dcim.platforms.get(slug=platform)

        # IP Adresse des Gerätes aus Verbindung holen
        ip_address_str = str(dev.connections['cli'].ip)+"/24"

        # Schauen ob IP Adresse in Netbox existiert, wenn nicht, dann erstellen
        if not nb.ipam.ip_addresses.filter(address=ip_address_str):
                print(f"[+] IP Address not in Netbox, creating {ip_address_str}")
                nb.ipam.ip_addresses.create(address=ip_address_str, status='online', description=f"Auto-Discovered IP Address for {hostname}")

        # Prefix des Gerätes aus IP Adresse holen und schauen ob Prefix in Netbox existiert
        prefix_str = str(ip_network(ip_address_str, strict=False).supernet().network_address)+"/24"
        print(f"[*] Checking for Prefix {prefix_str}")
        prefix_nb = nb.ipam.prefixes.get(prefix=prefix_str)
        st = setSite(prefix_nb, prefix_str)

        # Schauen ob Platform in Netbox existiert, wenn nicht, dann erstellen
        if not platform_chk:
                print(f"[+] Platform not in Netbox, creating {platform}")
                nb.dcim.platforms.create(name=platform, slug=platform)
                tmp = nb.dcim.platforms.get(slug=platform)
                pf = tmp.id
        else:
                tmp = nb.dcim.platforms.get(slug=platform)
                pf = tmp.id

        # Dasselbe für Device Type
        if not device_type_chk:
                print(f"[+] Device Type not in Netbox, creating {chassis}")
                nb.dcim.device_types.create(model=chassis, slug=chassis, manufacturer=1)
                tmp = nb.dcim.device_types.get(slug=chassis)
                dt = tmp.id
        else:
                tmp = nb.dcim.device_types.get(slug=chassis)
                dt = tmp.id

        # OS und OS Version zusammenfügen
        os_full = os + " " + os_ver

        # Objekt für das Gerät aus Netbox holen
        host = nb.dcim.devices.get(name=hostname)

        # Wenn Gerät in Netbox existiert, dann Daten updaten, ansonsten erstellen
        if host:
                print(f"[*] Device {hostname} is already in netbox, updating data")
                host.device_type = dt
                host.platform = pf
                host.serial = serial_num
                host.site = st
                host.custom_fields={'OS':os_full} # Bei verschachtelten Fields muss dass so gemacht werden
                host.save()
        else:
                print(f"[*] Device {hostname} is not in netbox, creating it now")
                nb.dcim.devices.create(name=hostname, device_type=dt, platform=pf, serial=serial_num, role=1, status='active', site=st, custom_fields={'OS':os_full}, primary_ip4=None, primary_ip6=None)
                host = nb.dcim.devices.get(name=hostname) # Host Objekt neu holen, da es vorher nicht existiert hat
                print(f"[+] Device {hostname} created with ID {host.id} created")

        # ---- Interfaces in Netbox erstellen und ergänzen ----
        print(f"[*] Adding interfaces to {hostname}")
        # Für jede Interface im Interface Dictionary
        for interface_name, interface_data in intpar.items():
                netbox_type = sortInterface(interface_name)

                # MTU Wert bestimmen, wenn vorhanden
                if 'mtu' in interface_data:
                        mtu_ph = interface_data['mtu']
                else:
                        mtu_ph = None

                # Wenn Interface in Netbox existiert, dann 'interface' setzen, ansonsten erstellen
                cdp_int = nb.dcim.interfaces.get(name=interface_name, device_id=host.id)
                if cdp_int != None:
                        if interface_name == cdp_int.name:
                                print(f"[-] Interface {interface_name} already exists on Device {hostname}")
                                interface = nb.dcim.interfaces.get(name=interface_name, device_id=host.id)
                else:
                        print(f"[+] Creating Interface {interface_name}")
                        interface = nb.dcim.interfaces.create(type=netbox_type, name=interface_name, device=host.id, enabled=interface_data['enabled'], mtu=mtu_ph)

                # Wenn IP Konfiguration für Interface vorhanden
                if 'ipv4' in interface_data:
                                print(f"[->] Found IP Conifguration on Interface")
                                for ip_address in interface_data['ipv4']:
                                                # Addressenobjekt vom Host aus Netbox holen
                                                ipint = nb.ipam.ip_addresses.get(address=ip_address)

                                                # Wenn IP Adresse schon einem Objekt zugewiesen ist, dann nichts machen, ansonsten zuweisen
                                                if ipint.assigned_object_id:
                                                        print(f"[-] IP Address {ip_address} already assigned to {ipint.assigned_object_type} with ID {ipint.assigned_object_id}")
                                                else:
                                                        print(f"[+] Assigning IP Address {ip_address} to Interaface {interface_name}")
                                                        ipint.assigned_object_id = interface.id
                                                        ipint.assigned_object_type = "dcim.interface"
                                                        ipint.save()

                                                        print(f"[+] Setting Primary IP Address {ip_address} on Device {hostname}")
                                                        ipset = nb.dcim.devices.get(name=hostname)
                                                        ipset.primary_ip4 = ipint.id
                                                        ipset.save()

        # ---- CDP Nachbarn in Netbox erstellen und ergänzen ----
        print(f"[*] Checking CDP Neighbors for {hostname}...")
        removeLooseCables()
        # Für jeden CDP Nachbarn
        for index, device_info in cdppar['index'].items():
                # Daten aus CDP Nachbar extrahieren und korrekt formatieren
                cdp_device_id = device_info.get('device_id', 'N/A')
                cdp_device_role = device_info.get('capabilities', 'N/A')
                cdp_device_role_slug = cdp_device_role.lower().replace(' ', '_')
                cdp_device_type = device_info.get('platform', 'N/A').replace('cisco ', '')
                cdp_device_type_slug = cdp_device_type.replace(' ', '_')
                cdp_platform = re.sub('^WS-', '', cdp_device_type).split('-')[0]
                cdp_local_interface = device_info.get('local_interface', 'N/A')
                cdp_port_id = device_info.get('port_id', 'N/A')
                management_addresses = device_info.get('management_addresses', {})
                if management_addresses:
                        cdp_mgmt_ip = next(iter(management_addresses))

                # Wenn Platform in Netbox existieren, dann ID holen, ansonsten erstellen
                if not nb.dcim.platforms.filter(slug=cdp_platform.lower()):
                        print(f"[+] Platform {cdp_platform} not in Netbox, creating it now")
                        nb.dcim.platforms.create(name=cdp_platform, slug=cdp_platform.lower())
                        tmp = nb.dcim.platforms.get(slug=cdp_platform.lower())
                        pf = tmp.id
                else:
                        tmp = nb.dcim.platforms.get(slug=cdp_platform.lower())
                        pf = tmp.id

                # Hier dasselbe für Device Type
                if not nb.dcim.device_types.filter(slug=cdp_device_type_slug.lower()):
                        print(f"[+] Device Type {cdp_device_type} not in Netbox, creating it now")
                        nb.dcim.device_types.create(model=cdp_device_type, slug=cdp_device_type_slug.lower(), manufacturer=1)
                        tmp = nb.dcim.device_types.get(slug=cdp_device_type_slug.lower())
                        dt = tmp.id
                else:
                        tmp = nb.dcim.device_types.get(slug=cdp_device_type_slug.lower())
                        dt = tmp.id

                # Wenn IP Adresse des Nachbarn in Netbox nicht existiert, dann erstellen
                if not nb.ipam.ip_addresses.filter(address=cdp_mgmt_ip+"/24"):
                        print(f"[+] IP Address {cdp_mgmt_ip}/24 not in Netbox, creating it now")
                        nb.ipam.ip_addresses.create(address=cdp_mgmt_ip+"/24", status='online', description=f"Auto-Discovered IP Address for {cdp_device_id}")
                else:
                        print(f"[-] IP Address {cdp_mgmt_ip}/24 already in Netbox")

                cdp_ipint = nb.ipam.ip_addresses.get(address=cdp_mgmt_ip+"/24")

                # 'Capabilities' als Device Role in Netbox erstellen wenn nicht vorhanden
                if not nb.dcim.device_roles.filter(slug=cdp_device_role_slug):
                        print(f"[+] Role {cdp_device_role} not in Netbox, creating it now")
                        nb.dcim.device_roles.create(name=cdp_device_role, slug=cdp_device_role_slug, color=pickColor())
                        tmp = nb.dcim.device_roles.get(slug=cdp_device_role_slug)
                        rl = tmp.id
                else:
                        tmp = nb.dcim.device_roles.get(slug=cdp_device_role_slug)
                        rl = tmp.id

                # Prefix des Nachbarn aus IP Adresse holen und schauen ob Prefix in Netbox existiert
                prefix_str = str(ip_network(cdp_mgmt_ip+"/24", strict=False).supernet().network_address)+"/24"
                print(f"[*] Checking for Prefix {prefix_str}")
                prefix_nb = nb.ipam.prefixes.get(prefix=prefix_str)
                st = setSite(prefix_nb, prefix_str)

                # Wenn Device in Netbox nicht existiert, dann erstellen, ansonsten Daten updaten
                if not nb.dcim.devices.filter(name=cdp_device_id):
                        print(f"[+] Device {cdp_device_id} not in Netbox, creating it now")
                        nb.dcim.devices.create(name=cdp_device_id, device_type=dt, platform=pf, role=rl, status='active', site=st, primary_ip4=None, primary_ip6=None)
                else:
                        print(f"[*] Device {cdp_device_id} already in Netbox, updating data")
                        cdp_device_host = nb.dcim.devices.get(name=cdp_device_id)
                        cdp_device_host.device_type = dt
                        cdp_device_host.platform = pf
                        cdp_device_host.role = rl
                        cdp_device_host.site = st
                        cdp_device_host.save()

                if not nb.dcim.interfaces.filter(name=cdp_local_interface, device_id=host.id):
                        netbox_type = sortInterface(cdp_local_interface)

                        print(f"[+] Interface {cdp_local_interface} not in Netbox, creating it now")
                        nb.dcim.interfaces.create(name=cdp_local_interface, device=host.id, type=netbox_type, enabled=True)
                else:
                        print(f"[-] Interface {cdp_local_interface} already in Netbox")

                # Wenn Interface des Nachbarn in Netbox nicht existiert, dann erstellen
                if not nb.dcim.interfaces.filter(name=cdp_port_id, device=cdp_device_id):
                        netbox_type = sortInterface(cdp_port_id)

                        print(f"[+] Interface {cdp_port_id} not in Netbox, creating it now")
                        cdp_device_host = nb.dcim.devices.get(name=cdp_device_id)
                        nb.dcim.interfaces.create(name=cdp_port_id, device=cdp_device_host.id, type=netbox_type, enabled=True)

                        cdp_port_id_int = nb.dcim.interfaces.get(name=cdp_port_id, device_id=cdp_device_host.id)
                        cdp_local_interface_int = nb.dcim.interfaces.get(name=cdp_local_interface, device_id=host.id)

                        if cdp_ipint.assigned_object_id:
                                print(f"[-] IP Address {cdp_mgmt_ip}/24 already assigned to {cdp_ipint.assigned_object_type} with ID {cdp_ipint.assigned_object_id}")
                        else:
                                print(f"[+] Assigning IP Address {cdp_mgmt_ip}/24 to Interaface {cdp_port_id}")
                                cdp_ipint.assigned_object_id = cdp_port_id_int.id
                                cdp_ipint.assigned_object_type = "dcim.interface"
                                cdp_ipint.save()

                                print(f"[+] Setting Primary IP Address {cdp_mgmt_ip}/24 on Device {cdp_device_id}")
                                cdp_ipset = nb.dcim.devices.get(name=cdp_device_id)
                                cdp_ipset.primary_ip4 = cdp_ipint.id
                                cdp_ipset.save()
                else:
                        print(f"[-] Interface {cdp_port_id} already in Netbox")

                # Kabel zwischen Interface und Port erstellen, wenn nicht vorhanden
                # Richtig komisch, dass die filter keys anders sind als die, die ich beim erstellen setze
                cdp_port_id_int = nb.dcim.interfaces.get(name=cdp_port_id, device_id=cdp_device_host.id)
                cdp_local_interface_int = nb.dcim.interfaces.get(name=cdp_local_interface, device_id=host.id)
                existing_cables = nb.dcim.cables.filter(termination_a_id=cdp_local_interface_int.id, termination_b_id=cdp_port_id_int.id)
                if not existing_cables:
                        print(f"[+] Creating Cable between {cdp_local_interface} and {cdp_port_id}")
                        nb.dcim.cables.create(a_terminations=[{'object_type':'dcim.interface','object_id':cdp_local_interface_int.id}], b_terminations=[{'object_type':'dcim.interface','object_id':cdp_port_id_int.id}], status='connected')
                else:
                        print(f"[-] Cable between {cdp_local_interface} and {cdp_port_id} already exists")
        print(f"[***] Finished processing {hostname}")

# ---- Parsing und Verarbeitung der Daten ----
for device_name,device in tb.devices.items():
        discoverCiscoDevice(nb,tb,device_name)
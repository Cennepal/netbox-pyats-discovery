from extras.scripts import Script, StringVar
from dcim.models import Device, DeviceRole, DeviceType, Site, Interface
from ipam.models import IPAddress

# Dieses Skript nimmt zwei Variablen entgegen, den Gerätenamen und die IP-Adresse.
# Es erstellt dann das Gerät in Netbox mit der Interface Vlan1, der die IP-Adresse zugewiesen wird, und setzt sie schließlich als primäre IP-Adresse.
class NetboxTestbedMaker(Script):
    class Meta:
        name = "Netbox Device Maker"
        description = "Create a barebone device in Netbox for further use by Cisco Discovery script."

    dev_name = StringVar(label="Device Hostname", description="Enter the hostname precisely!")
    dev_ip = StringVar(label="Device IP", description="Enter the IP address of the device.")

    def run(self, data, commit):
        dev_role = DeviceRole.objects.get(name="Switch")
        dev_type = DeviceType.objects.get(model="Unknown")
        site_name = Site.objects.get(name="unknown")
        dev_ip_cidr = data['dev_ip'] + "/24"

        if Device.objects.filter(name=data['dev_name']):
            self.log_info("Device already exists: " + data['dev_name'])
            device = Device.objects.get(name=data['dev_name'])
        else:
            self.log_info("Device created: " + data['dev_name'])
            device = Device(name=data['dev_name'], role=dev_role, device_type=dev_type, site=site_name, status='active')
            device.save()

        if IPAddress.objects.filter(address=dev_ip_cidr):
            self.log_info("IP already exists: " + dev_ip_cidr)
            ip = IPAddress.objects.get(address=dev_ip_cidr)
        else:
            self.log_info("IP created: " + dev_ip_cidr)
            ip = IPAddress(address=dev_ip_cidr, status='online')
            ip.save()

        if Interface.objects.filter(device=device.id, name="Vlan1"):
            interface = Interface.objects.get(device=device.id, name="Vlan1")
            self.log_info("Interface already exists: " + data['dev_name'] + " Vlan1")
        else:
            interface = Interface(device=device, name="Vlan1")
            interface.save()
            self.log_info("Interface created: " + data['dev_name'] + " Vlan1")

        if ip.interface is None:
            ip.interface = interface
            ip.save()

        if interface.device is None:
            interface.device = device
            interface.save()

        if ip.assigned_object_id is None:
            interface.ip_addresses.add(ip)
        
        if device.primary_ip4 is None:
            device.primary_ip4 = ip
            device.save()

        self.log_info("Device created: " + data['dev_name'])
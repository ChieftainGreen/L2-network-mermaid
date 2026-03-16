"""
LibreNMS L2 topology collector.

This script:
1. Queries LibreNMS API for devices, ports and L2 links (CDP/LLDP)
2. Resolves device_id -> hostname
3. Resolves port_id -> ifName
4. Builds normalized link dictionary
5. Deduplicates A<->B links
6. Provides placeholder for additional processing
7. Prints final topology dictionary

Author: network automation prototype
"""
from collections import Counter
import requests
from icecream import ic
import re
from dotenv import load_dotenv
import os

# nexus подключены mgmt0 друг к другу? или куда?
# DMZ1 po1 -> native vlan 500 !
# !нужно находить и ликвидировать транки с native vlan default 1 - через них протекают lldp?
# маки 0314 и 0315 нужно фильтровать. Или не? не, пусть явно включают lldp

# DONE сейчас empty_platform фильтрует токи доступа. сделать отдельно
# DONE платформа пустая у всех кто не в NMS! это неправильно. testrtr, точки  - нужны

# DONE не отрабатывает LLDP/CDP cleanup - например 77-x-12 цепляется к dmz и acc1 сразу, это в librenms


# ---------------------------
# CONFIG - default variables, overwritten with dotenv
# ---------------------------

load_dotenv()
def getenv_bool(name: str, default: bool = False) -> bool:
    """Convert environment variable to bool."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


LIBRENMS_URL = os.getenv("LIBRENMS_URL", "http://librenms")
API_TOKEN = os.getenv("API_TOKEN")

COLLAPSE_PARALLEL_LINKS = getenv_bool("COLLAPSE_PARALLEL_LINKS", True) # показывать |3 links| вместо 3 линий между парой соседей
SHOW_PARALLEL_PORTS = getenv_bool("SHOW_PARALLEL_PORTS", False) # если тру, то вместо |3 links| перечислять все порты
PRINT_REMOTE_INFOx3 = getenv_bool("PRINT_REMOTE_INFOx3", False) # дополнительный принт remote platform, version, hw

SKIP_EMPTY_PLATFORM = getenv_bool("SKIP_EMPTY_PLATFORM", True) # False to view IPhones etc
PRINT_SHORT_DICTS = getenv_bool("PRINT_SHORT_DICTS", True) # чтобы влезало в строку

EXCLUDE_DEVICES = getenv_bool("EXCLUDE_DEVICES", True) # TODO 'if' is not impemented yet
EXCLUDE_LINKS = getenv_bool("EXCLUDE_LINKS", True) # TODO 'if' is not impemented yet

SHORT_KEYS = ['local_host', 
              'local_port', 
              'remote_host', 
              'remote_port',
              'protocol']

ic.disable()



HEADERS = {
    "X-Auth-Token": API_TOKEN,
    "Content-Type": "application/json"
}


# ---------------------------
# API FUNCTIONS
# ---------------------------

def get_devices():
    """Fetch devices list from LibreNMS"""
    url = f"{LIBRENMS_URL}/api/v0/devices"
    r = requests.get(url, headers=HEADERS, verify=False)
    r.raise_for_status()

    data = r.json()["devices"]

    device_map = {}

    for d in data:
        device_map[d["device_id"]] = {
            "hostname": d["hostname"],
            "platform": d.get("hardware", "unknown")
        }

    return device_map

def get_ports():
    """Fetch ports list from LibreNMS"""
    url = f"{LIBRENMS_URL}/api/v0/ports"
    r = requests.get(url, headers=HEADERS, verify=False)
    r.raise_for_status()

    data = r.json()["ports"]

    port_map = {}

    for p in data:
        port_map[p["port_id"]] = p["ifName"]

    return port_map

def get_links():
    """Fetch CDP/LLDP links"""
    url = f"{LIBRENMS_URL}/api/v0/resources/links"
    r = requests.get(url, headers=HEADERS, verify=False)
    r.raise_for_status()

    return r.json()["links"]

# ---------------------------
# BUILD TOPOLOGY
# ---------------------------

def build_links(links, device_map, port_map):
    """Build normalized topology dictionary"""

    result = []

    for link in links:

        local_device = device_map.get(link["local_device_id"], {})
        remote_device = device_map.get(link.get("remote_device_id"), {})

        #pseudotype = remote_device.get("platform")
        #if remote_device.get("platform") is None or remote_device.get("platform") =='': # remote device is not in LibreNMS
        #    if link.get("remote_platform") is None or link.get("remote_platform") =='': # remote device has empty "remote plaform" (not CDP)
        #        pseudotype = link.get("remote_version") # then go to LLDP remote version
        #        #pseudotype = None
        #    else:
        #        pseudotype = link.get("remote_platform")
        #else:
        #    #pseudotype = None
        #    pseudotype = remote_device.get("platform") # remote device IS in LibreNMS - we know all
        
        #probably_mac = link.get("remote_port")
        #try:
        #    probably_mac = probably_mac.split()[6]
        #    probably_mac = probably_mac.replace("(","")
        #    probably_mac = probably_mac.replace(")","")
        #except:
        #    pass
        
        #if link.get("remote_hostname") is None or link.get("remote_hostname") =='': # remote device name empty (lldp)
        #    pseudoname = f'{pseudotype.split()[0]} + {probably_mac}'
        #else:
        #    pseudoname = link.get("remote_hostname")
            
        entry = {
            "local_host": local_device.get("hostname"),
            "local_port": port_map.get(link["local_port_id"]),
            "remote_host": remote_device.get("hostname", link.get("remote_hostname")), # имя remote в libreNMS
            #"remote_self_name": link.get("remote_hostname"), # имя из cdp/lldp, как оно настроено на девайсе
            "remote_port": port_map.get(link["remote_port_id"], link.get("remote_port")),
            #"remote_port": link.get("remote_port"),
            "protocol": link.get("protocol"),
            "local_platform": local_device.get("platform"),
            #"remote_platform": remote_device.get("platform"),
            #"pseudotype" : pseudotype,
            #"pseudoname" : pseudoname,
            "remote_platform": remote_device.get("platform"),
            "remote_version": link["remote_version"]
            #"lid" : local_device.get("local_port_id"),
            #"rid" : local_device.get("remote_port_id")  #wrong
        }
        
        #ic.enable()
        #if entry['remote_host'].split(".")[0] != entry['remote_orig'].split(".")[0]:
        #    ic (entry)
        # try to compose name from misc info.
        # we need individual blocks for each remote device
        # also Mermaid is bad with "(" and ")".

        
        #if entry['remote_host'] == 'null':
        #    entry['remote_host'] = entry['remote_platform'].split()[0] + probably_mac
        #if entry['remote_host'] == 'null':
        #    entry['remote_host'] = entry['remote_version'].split()[0] + probably_mac
        #if entry['remote_host'] == 'null':
        #    entry['remote_host'] 

        result.append(entry)

    return result

# ---------------------------
# DEDUPLICATION
# ---------------------------

def deduplicate_links(links):
    """
    Remove duplicated links (A->B and B->A)
    """
    seen = set()
    deduped = []
    for link in links:
        side_a = (link["local_host"], link["local_port"])
        side_b = (link["remote_host"], link["remote_port"])
        key = tuple(sorted([side_a, side_b]))

        if key not in seen:
            seen.add(key)
            deduped.append(link)
        else:
            ic (f'deduplicate deletes {key} , {link}')
    return deduped

def normalize_hostname(name):
    """
    Optional hostname normalization.
    Example:
    SW-VOZ-DMZ1.ww930.my-it-solutions.net -> SW-VOZ-DMZ1
    """
    if not name:
        return name
    name = name.upper()
    return name.split(".")[0]

def sanitize_id(name):
    """
    Mermaid node IDs cannot contain special characters.
    """
    return name.replace("-", "_").replace(".", "_")

def print_endpoint_hardware_stats(links):
    # TOFIX - считаются только remote! подсчет неверен! И еще было 70 Unknown - откуда вообще столько?
    """
    Print statistics of endpoint hardware types found in topology.
    """
    counter = Counter()
    for link in links:

        #print (link)
        #hw = link.get("remote_platform")
        hw = "UNKNOWN"
        #if not hw:
        if link.get("remote_platform") is None: # remote device has empty "remote plaform" (not CDP)
            hw = link.get("remote_version")[:15] # then go to LLDP remote version. 15 for huawei before /n
        else:
            hw = link.get("remote_platform")
            #hw = "UNKNOWN"
            
        
        # Original overwrite
        #hw = link.get("remote_platform")
        if PRINT_REMOTE_INFOx3:
            print (f'{link.get("remote_platform")}, {link.get("remote_version")[:15]}, {hw}')
        #if not hw:
        #    hw = "UNKNOWN"

        counter[hw] += 1
    print("\nEndpoint hardware statistics:\n")
    for hw, count in sorted(counter.items(), key=lambda x: x[1], reverse=True):
        print(f"{count:5}  {hw}")
    print(f"\nTotal unique hardware types: {len(counter)}")


# Exclude.conf  part ----------------------------
def load_exclude_rules(path="exclude_hosts.conf"):
    """
    Load exclude rules from config file.
    Format:
        key=value

    Example:
        name=labserver1
        hardware=Cisco IP Phone
    """
    rules = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                rules.append({
                    "key": key.strip().lower(),
                    "value": value.strip()
                })
    except FileNotFoundError:
        print("Exclude file not found, skipping filtering")

    print(f"Loaded {len(rules)} exclude rules")

    return rules

def load_exclude_links(path="exclude_links.conf"):
    """
    Load exclude rules from config file.
    Format:
        host1, host2

    Example:
        switch3=ispdevice1
    """
    linkrules = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "," not in line:
                    continue
                #print (line.split(",", 1))
                host1, host2 = line.split(",", 1)
                linkrules.append([
                    host1.strip().upper(),
                    host2.strip().upper()
                ])
    except FileNotFoundError:
        print("Exclude file not found, skipping filtering")
    print(f"Loaded {len(linkrules)} exclude rules")
    return linkrules

def apply_exclude_links(links, linkrules):
    """
    Remove links matching exclude rules.
    """
    print (linkrules)
    filtered = []
    removed = 0
    for link in links:
        removed_by = None
        #print (f'!!!!! LINKRULES ')
        for rule in linkrules:
            if (normalize_hostname(link['local_host']) in rule and
                normalize_hostname(link['remote_host']) in rule):
                #print (f'!!!!! LINKRULES {rule}')
                removed_by = rule
                break
        if removed_by:
            removed += 1
            print(
                f"Excluded link by {removed_by[0]}<->{removed_by[1]}: "
                f"{link['local_host']} {link['local_port']} -> "
                f"{link['remote_host']} {link['remote_port']}"
            )
            continue
        filtered.append(link)
    print(f"Total excluded links: {removed}")
    return filtered

def link_matches_rule(link, rule):
    """
    Check if link matches exclude rule.
    """
    key = rule["key"]
    value = rule["value"]
    if key == "name":
        if link["local_host"] and value in link["local_host"]:
            return True
        if link["remote_host"] and value in link["remote_host"]:
            return True
    if key == "hardware":
        if link.get("local_platform") and value in link["local_platform"]:
            return True
        if link.get("remote_platform") and value in link["remote_platform"]:
            return True
    return False

def apply_exclude_rules(links, rules):
    """
    Remove links matching exclude rules.
    """
    filtered = []
    removed = 0
    for link in links:
        removed_by = None
        for rule in rules:
            if link_matches_rule(link, rule):
                removed_by = rule
                break
        if removed_by:
            removed += 1
            print(
                f"Excluded by {removed_by['key']}={removed_by['value']}: "
                f"{link['local_host']} {link['local_port']} -> "
                f"{link['remote_host']} {link['remote_port']}"
            )
            continue
        filtered.append(link)
    print(f"Total excluded devices: {removed}")
    return filtered

# Exclude.conf  end ----------------------------

def mermaid_style_block():
    return """
classDef cable fill:#000,stroke:#000,stroke-width:2px,color:#000,font-size:0px, shape: f-circ
classDef device fill:#f5f5f5,stroke:#333,stroke-width:1px
linkStyle default stroke-width:2px
"""

def generate_mermaid(
        links,
        direction="LR",
        normalize_hosts=True,
        show_port_labels=True,
        readable_layout=True
):
    """
    Generate Mermaid Flowchart topology.

    Options
    -------
    direction:
        LR (left-right) or TB (top-bottom)

    normalize_hosts:
        remove domain part from hostname

    show_port_labels:
        show interface names on links

    readable_layout:
        adds spacing helpers
    """

    lines = []

    lines.append("flowchart " + direction)
    lines.append(mermaid_style_block())
    junction_count = 0
    nodes_defined = set()

    if COLLAPSE_PARALLEL_LINKS:
        groups = group_parallel_links(links)
    else:
        groups = {i: [link] for i, link in enumerate(links)}

    for group in groups.values():

        first = group[0]

        host_a = first["local_host"]
        host_b = first["remote_host"]

        if normalize_hosts:
            host_a = normalize_hostname(host_a)
            host_b = normalize_hostname(host_b)

        id_a = sanitize_id(host_a)
        id_b = sanitize_id(host_b)

        if id_a not in nodes_defined:
            lines.append(f'{id_a}["{host_a}"]')
            lines.append(f"class {id_a} device")
            nodes_defined.add(id_a)

        if id_b not in nodes_defined:
            lines.append(f'{id_b}["{host_b}"]')
            nodes_defined.add(id_b)

        junction_id = f"J{junction_count}"
        junction_count += 1

        #lines.append(f'{junction_id}(( ))')
        #lines.append(f"class {junction_id} cable")
        lines.append(f'{junction_id}@{{shape: f-circ}}')

        # SINGLE LINK
        if len(group) == 1 or not COLLAPSE_PARALLEL_LINKS:

            link = group[0]

            port_a = link["local_port"]
            port_b = link["remote_port"]

            label_a = f"|{port_a}|" if show_port_labels else ""
            label_b = f"|{port_b}|" if show_port_labels else ""

        # COLLAPSED LINKS
        else:

            count = len(group)

            if SHOW_PARALLEL_PORTS:

                ports_a = ",".join(l["local_port"] for l in group)
                ports_b = ",".join(l["remote_port"] for l in group)

                label_a = f"|{ports_a}|"
                label_b = f"|{ports_b}|"

            else:

                label_a = f"|{count} links|"
                label_b = ""

        lines.append(f"{id_a} --{label_a}--- {junction_id}")
        lines.append(f"{junction_id} --{label_b}--- {id_b}")

        if readable_layout:
            lines.append("")

    return "\n".join(lines)

def remove_links_without_platform(links):
    """
    Remove links where remote_platform is None or empty.
    Usually these are endpoints (phones, printers, etc.)
    Fake LLDP connections
    """

    filtered = []
    for link in links:
        #ic.enable()
        #ic (link)
        if link.get("remote_platform") == '' or link.get("remote_platform") is None:
            print(
                f"Removing endpoint link (name may be LibreNMS error): "
                f"{link['local_host']} {link['local_port']} -> "
                f"{link['remote_host']} {link['remote_port']} "
                f"(no platform)"
            )
            continue
        if link.get("remote_version") == '' or link.get("remote_version") is None:
            print(
                f"Removing endpoint link (name may be LibreNMS error): "
                f"{link['local_host']} {link['local_port']} -> "
                f"{link['remote_host']} {link['remote_port']} "
                f"(no platform)"
            )
            continue
        filtered.append(link)
    return filtered

def remove_cdp_when_lldp_exists(links):
    """
    If both CDP and LLDP exist on same local port,
    keep LLDP and remove CDP.

    This fixes CDP traversing Juniper devices.
    """
    port_protocols = {}
    for link in links:
        key = (link["local_host"], link["local_port"])
        port_protocols.setdefault(key, set()).add(link["protocol"])
    filtered = []
    for link in links:
        key = (link["local_host"], link["local_port"])
        protocols = port_protocols[key]
        if "lldp" in protocols and link["protocol"] == "cdp":
            print(
                f"Removing CDP shadow link: "
                f"{link['local_host']} {link['local_port']} -> "
                f"{link['remote_host']} {link['remote_port']}"
            )
            continue
        filtered.append(link)
    return filtered

def process_tricky_devices(links):
    
    # подлые устройства:
    # 1) Телефоны Siemens - видны в lldp - в имя librenms подставляет имя какого-то свитча (ПОДЛО), 
    # но remote platform None, verison ''. Это телефоны сименс. 
    # Решение: определяем по remote version '' + platform None, переписываем name NONAME + порт - там мак
    # 2) Emulex - имя,platform 'null', version содрежит строку с Emulex...
    # решение: определяем по version Emulex, делаем имя из Emulex + remote port
    # 3) nexus2 1/7 - имя,platform и version 'null', есть только remote port (mac)
    # Решение: аналогично 1

    # но бывают хорошие точки доступа, у них remote platform тоже null.    
    for link in links:
        probably_mac = link.get("remote_port")
        try:
            probably_mac = probably_mac.split()[6]
            probably_mac = probably_mac.replace("(","")
            probably_mac = probably_mac.replace(")","")
        except:
            pass
        
        if link.get("remote_version") == '' or link.get("remote_version") == 'null':
            if link.get("remote_platform") is None:
                #print (link.get("remote_port"))
                newname = f'NONAME' + probably_mac
                link['tricky'] = link['remote_host']
                link['remote_host'] = newname
                print (f'Found tricky device, set name to {link["remote_host"]}')
        
        if link.get("remote_version").startswith('Emulex'):
            link['tricky'] = link['remote_host']
            link['remote_host'] = f'Emulex{probably_mac}'
            print (f'Found tricky device, set name to {link["remote_host"]}')
    return links

def find_port_macs(links):
    for link in links:
        probably_mac = link.get("remote_port")
        probably_mac = probably_mac.replace(" ", ":")
        probably_mac = probably_mac[:17]
        print (probably_mac)
        #probably_mac = probably_mac.upper()
        pattern_mac = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
        if re.match(pattern_mac, probably_mac, re.IGNORECASE):
            print (f'Found remote device {link.get("remote_host")} port is actually a MAC address')
            link['remote_port'] = 'nope'
        else:
            pass
    return links
# ---------------------------
# PLACEHOLDER FOR FUTURE EDITS
# ---------------------------

def process_links(links):
    """
    Placeholder for additional topology processing.

    Examples of future tasks:
    - remove access switches
    - collapse LAG interfaces
    - filter only specific locations
    - normalize hostnames
    """


    print("\nLoading exclude rules...")
    rules = load_exclude_rules()
    linkrules = load_exclude_links()

    #print("\nClearing dull devices Stage 1 ") 
    #links = remove_dull_stage1(links)

    if rules:
        print("\nApplying exclude-device rules...")
        links = apply_exclude_rules(links, rules)

    if linkrules:
        print("\nApplying exclude-link rules...")
        links = apply_exclude_links(links, linkrules)
    
    if SKIP_EMPTY_PLATFORM:    
        print("\nFiltering links without platform...")
        links = remove_links_without_platform(links) # clear links to remote devices with no platform and version

    print("\Processing links to tricky devices...")
    links = process_tricky_devices(links)

    print("Finding incorrect LLDP port names...")
    links = find_port_macs(links)

    print("\nRemoving CDP duplicates when LLDP exists...")
    links = remove_cdp_when_lldp_exists(links) # can be solved by correct unused native vlan

    return links

def group_parallel_links(links):
    """
    OPTIONAL - Group links between same pair of hosts
    """

    groups = {}

    for link in links:

        host_a = link["local_host"]
        host_b = link["remote_host"]
        key = tuple(sorted([host_a, host_b]))
        groups.setdefault(key, []).append(link)

    return groups



# ---------------------------
# MAIN
# ---------------------------

def main():

    print("Fetching devices...")
    devices = get_devices()

    print("Fetching ports...")
    ports = get_ports()

    print("Fetching links...")
    links = get_links()

    print("Building topology...")
    topology = build_links(links, devices, ports)

    print("Processing...")
    topology = process_links(topology)
    
    print("Deduplicating...")
    topology = deduplicate_links(topology)



    print("\nFinal topology:\n")

    for link in topology:
        if PRINT_SHORT_DICTS:
            for key in SHORT_KEYS:
                if key in link:
                    print(f"{key}: {link[key]}, ", end='')
            print()
        else:
            print(link)


    print("\nGenerating Mermaid diagram...\n")

    mermaid = generate_mermaid(
        topology,
        direction="LR",
        normalize_hosts=True,
        show_port_labels=True,
        readable_layout=True
    )

    print(mermaid)

    print_endpoint_hardware_stats(links)

if __name__ == "__main__":
    main()

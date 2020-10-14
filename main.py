'''
Copyright (c) 2020 Cisco and/or its affiliates.

This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at

               https://developer.cisco.com/docs/licenses

All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
'''


import ansible_runner, yaml
from datetime import datetime

# read the target devices from the hosts file and store them in a list
with open('inventory/hosts') as f:
    doc = f.read()
hosts_list = doc.split('\n')
hosts_list = list(filter(None, hosts_list))
print(hosts_list)

# updates the txt files in which the results of the playbooks are stored with the current date and time, deletes previous data
file_list = ['interfaces_ok.txt', 'interfaces_down.txt', 'interfaces_counters.txt']
now = datetime.now().strftime("%Y-%m-%d %H:%M")
for file in file_list:
    with open(file, 'w') as f:
        f.write("[" + str(now) + "]\n")

# iterate over the list of target devices to run each playbook on each device
for host in hosts_list:

    # overwrite the inventory/hosts file with the target device of this iteration of the loop
    # because the ansible_runner module is configured to read the target device from the inventory/hosts file
    with open('inventory/hosts', 'w') as f:
        f.write(host)

    # ansible_runner runs the playbook specified as parameter and returns the result in an object
    r = ansible_runner.run(private_data_dir='.', playbook='playbook-show_ip_int_brief.yaml')

    # the returned object includes different events that describe different stages of the playbook execution
    # the event labeled "runner_on_ok" includes the output of the command 'show ip int brief' run in the playbook 'playbook-show_ip_int_brief.yaml'
    for each_host_event in r.events:
        if each_host_event['event'] == "runner_on_ok":

            # because we are iterating over a list of hosts,
            # there can be a transition event where the 'host' IP is not the same as the IP registered in the event ('node_ip')
            # those are irrelevant events which is why we only continue if the 'host' IP is the same as the 'node_ip'
            node_ip = str(each_host_event['event_data']['remote_addr'])
            if node_ip == host:

                # incorporate error handling
                # as there are multiple events named 'runner_on_ok' but only one includes the result of the playbook
                # others throw an error when defining the variable 'cmd_line_output_intbrief'
                try:

                    # retrieve the output of the command 'show ip int brief' in a variable
                    # the output is a multiline string
                    cmd_line_output_intbrief = each_host_event['event_data']['res']['stdout_lines'][0]

                    # convert the multiline string into a list of dictionaries on a per interface basis
                    interface_list = []
                    for line in cmd_line_output_intbrief:
                        x = ' '.join(line.split()).split(" ")
                        data = {
                            'host': host,
                            'interface': x[0],
                            'ip-address': x[1],
                            'ok?': x[2],
                            'method': x[3],
                            'status': x[4],
                            'protocol': x[5]
                        }
                        interface_list.append(data)
                    interface_list.pop(0)


                    # iterate over each dictionary of the list to determine whether an interface is up or down
                    # and depending on the result, store the interface in a list
                    int_ok = []
                    int_down = []
                    for item in interface_list:
                        if item['ip-address'] != 'unassigned': # filter out interfaces that have no IP assigned
                            if item['status'] == 'up' and item['protocol'] == 'up':
                                int_ok.append(item['interface'])
                            else:
                                int_down.append(item['interface'])


                    # write the results to the dedicated txt files (unless the files are empty)
                    if int_ok:
                        with open('interfaces_ok.txt', 'a') as file:
                            file.write(host + ": " + ', '.join(int_ok) + '\n')
                    if int_down:
                        with open('interfaces_down.txt', 'a') as file:
                            file.write(host + ": " + ', '.join(int_down) + '\n')


                    # LOGIC FOR NEXT PLAYBOOK STARTS HERE, executed on same host
                    # to get error counters per interface per host
                    # requires a list of interfaces to execute the command in the playbook 'playbook-show_int_error_counters.yaml' per interface
                    # retrieved from the dictionaries describing each interface in the 'interface_list' variable, by interface name
                    interfaces = []
                    for item in interface_list:
                        interfaces.append(item['interface'])

                    # the interfaces need to be written to env/extravars for the playbook to access them
                    with open('env/extravars') as f:
                        doc = yaml.load(f, Loader=yaml.FullLoader)
                    doc['interfaces'] = interfaces
                    with open('env/extravars', 'w') as f:
                        yaml.dump(doc, f)

                    # execute the playbook 'playbook-show_int_error_counters.yaml'
                    s = ansible_runner.run(private_data_dir='.', playbook='playbook-show_int_error_counters.yaml')

                    # empty list in which the output of the commands run on a per interface basis are collected
                    interface_counters_list = []

                    # same logic as for the ansible_runner object commencing in line 49
                    # difference: the event that stores the output is now called 'runner_item_on_ok'
                    # because we iterate over multiple interfaces (labeled as 'item' in the playbook) and each has their own event to store the output
                    for each_host_event_s in s.events:
                        if each_host_event_s['event'] == "runner_item_on_ok":
                            node_ip_s = str(each_host_event_s['event_data']['host'])
                            if node_ip_s == host:

                                # get the interface on which the command was running
                                checked_interface = each_host_event_s['event_data']['res']['item']

                                # get the output of the command 'show interface 'INTERFACE-NAME' | i errors', with INTERFACE-NAME = 'checked_interface'
                                # the output is a multiline string
                                checked_interface_result = each_host_event_s['event_data']['res']['stdout_lines'][0]

                                # convert the multiline string into a dictionary and add it to the list collecting all per interface dictionaries
                                checked_interface_result_str = ', '.join(checked_interface_result)
                                checked_interface_result_list = checked_interface_result_str.split(",")
                                checked_interface_result_list_clean = map(lambda x: x.lstrip() , checked_interface_result_list)
                                data_s = {
                                    'interface': checked_interface
                                }
                                for item_s in checked_interface_result_list_clean:
                                    value = item_s.split(' ', 1)[0]
                                    key = item_s.split(' ', 1)[1]
                                    data_s[key] = int(value)
                                interface_counters_list.append(data_s)


                    # to summarize the data of the list of interface dictionaries,
                    # we create an empty dictionary to aggregate information
                    aggregated_counters = {
                        'host': host,
                        'ignored': 0,
                        'ignored_ints': [],
                        'input errors': 0,
                        'input errors_ints': [],
                        'collisions': 0,
                        'collisions_ints': [],
                        'frame': 0,
                        'frame_ints': [],
                        'CRC': 0,
                        'CRC_ints': [],
                        'interface resets': 0,
                        'interface resets_ints': [],
                        'output errors': 0,
                        'output errors_ints': [],
                        'overrun': 0,
                        'overrun_ints': []
                    }

                    # the variable 'changed_aggregated_counters' changes to True
                    # if a counter in the 'aggregate_counter' dictionary is changed (see line 192)
                    changed_aggregated_counters = False

                    # for each interface dictionary in the interface_counters_list,
                    # we add the value for the different counters to the counters in the 'aggregate_counter' dictionary
                    for interface_items in interface_counters_list:
                        for k in interface_items.keys():
                            for l in aggregated_counters.keys():
                                if k == l:

                                    # if a certain counter on an interface is NOT 0, i.e. there was a change,
                                    # the value is added to the value of aggregate counters in the 'aggregate_counter' dictionary,
                                    # and the interface name is added to a list for that counter in that dictionary
                                    if interface_items.get(k) != 0:
                                        changed_aggregated_counters = True
                                        aggregated_counters[k] += interface_items.get(k)
                                        add_interface_to_list = interface_items['interface']
                                        key_name = k + "_ints"
                                        aggregated_counters[key_name].append(add_interface_to_list)


                    # write the result stored in the 'aggregate_counter' dictionary to the dedicated output txt file
                    # only if the dictionary was changed, i.e. if there were any counters detected on any interface
                    if changed_aggregated_counters == True:

                        # provide the host information in the txt file to start with
                        with open('interfaces_counters.txt', 'a') as file:
                            file.write("On " + host + " the following error counters were detected: \n")

                        # iterate over each key-value pair in the 'aggregate_counter' dictionary, and
                        # add it to the output txt file IF THE VALUE OF THE AGGREGATE COUNTER IS NOT 0
                        # (i.e. a counter must have been counted on at least one of the interfaces on the host to be included in the output file)
                        # and list the interfaces on which the counters were counted on
                        for m in aggregated_counters.keys():
                            if isinstance(aggregated_counters.get(m), int):
                                if aggregated_counters.get(m) != 0:
                                    key_name = m + "_ints"
                                    int_string = ', '.join(aggregated_counters.get(key_name))
                                    with open('interfaces_counters.txt', 'a') as file:
                                        file.write("- " + str(aggregated_counters.get(m)) + " " + m + " in total, counted on: " + int_string + "\n")

                # part of error handling from line 61
                # if an error occurs, the script will jump into this code block
                # the continue statement instructs the script to ignore the error and continue with the code execution
                except:
                    continue

# when the script has reached this point,
# it jumps back to line 37 to run the exact same code block for the next host
# until all hosts that were listed in inventory/hosts (and therefore in the 'hosts_list' list) are covered

# at the end of the script, the inventory/hosts file is reverted to its initial state
# remember it is changed in lines 41-42 to only run each playbook on one host
revert_hosts_file = ""
for revert_host in hosts_list:
    revert_hosts_file += revert_host
    revert_hosts_file += '\n'
with open('inventory/hosts', 'w') as f:
    f.write(revert_hosts_file)

# also the interfaces that were written to env/extravars in lines 114-118 are deleted again for cleanliness
with open('env/extravars') as f:
    doc = yaml.load(f, Loader=yaml.FullLoader)
doc['interfaces'] = ""
with open('env/extravars', 'w') as f:
    yaml.dump(doc, f)
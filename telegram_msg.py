# Telegram python modules
import telepot
from telepot.loop import MessageLoop
# EPICS module
import epics
# Python module to manage CSV files
import pandas
# Auxiliary modules
import time, datetime, requests, sys, json
from threading import Thread, Lock

with open('config.json') as json_config:
    config = json.load(json_config)
# Defines Telegram Bot with unique Bot TOKEN
telegram_bot = telepot.Bot(sys.argv[1])

# Defines API credentials
api_user = sys.argv[2]
api_pass = sys.argv[3]

# Defines authorized personnel as global dictionaries
global authorized_personnel, teams
authorized_personnel = {}
teams = {}

# Defines dictionaries for PV monitoring
global PV_groups, PV_values, PV_mon
PV_groups = {}
PV_values = {}
PV_mon = {}

global mutex_PV, mutex_gp, mutex_user
mutex_PV = Lock()
mutex_gp = Lock()
mutex_user = Lock()
mutex_csv = Lock()


def send(chat_id, text_or_document, type, caption=None, parse_mode=None, disable_web_page_preview=None,
         disable_notification=None, reply_to_message_id=None, reply_markup=None):
    # Tries to send message or document to user, if internet connection falls keeps trying to send and logs information

    while True:
        try:
            # Verifies if message type is text or document,
            # case it is and succeeds to send the message, breaks out of while loop
            if type == "message":
                telegram_bot.sendMessage(chat_id, text_or_document, parse_mode, disable_web_page_preview,
                                         disable_notification, reply_to_message_id, reply_markup)
                break
            elif type == "document":
                telegram_bot.sendDocument(chat_id, text_or_document, caption, parse_mode,
                                          disable_notification, reply_to_message_id, reply_markup)
                break
            # Case it is an Unknown message type logs error and does not send anything
            else:
                log("Unknown Message Type", type)
                break
        # Case the chat_id does not exist or text message is empty breaks out of loop and logs error
        except telepot.exception.TelegramError:
            log("Telegram Error", "{while sending a message. Probably chat_id does not exist or message is empty.}", chat_id)
            break
        except NameError:
            break
        # Case something else occurs (most likely related to internet connection)
        # waits 60 seconds and tries to send the message again
        except Exception as exception:
            log(exception, text_or_document, chat_id)
            time.sleep(60)
            continue


def log(occurrence="", message="", user="", **kwargs):
    # Logging function

    msg_timestamp = kwargs.get('timestamp')
    # Formats error message
    if occurrence == "terminate":
        log_msg = '\n{} - BOT MANUALLY TERMINATED'.format(time.strftime("%d %b %Y %H:%M:%S",time.localtime()))
    else:
        if msg_timestamp:
            log_msg = '\n{} {} - {} - Message timestamp ({}) - {}'.format(time.strftime("%d %b %Y %H:%M:%S", time.localtime()), occurrence, user, time.strftime("%d %b %Y %H:%M:%S",time.localtime(msg_timestamp)), message)
        else:
            log_msg = '\n{} {} - {} - {}'.format(time.strftime("%d %b %Y %H:%M:%S", time.localtime()), occurrence, user, message)
    # Writes error message to errors.log file
    log_file = open('telegram_bot.log', 'a')
    log_file.write(log_msg)
    log_file.close()

def update_personnel():
    # Imports the authorized personnel from csv file

    # Imports global variables
    global authorized_personnel, teams
    # Imports CSV file as DataFrame
    authorized_personnel_df = pandas.read_csv('authorized_personnel.csv', keep_default_na=False)
    # Adds virtual teams to dictionaries
    authorized_personnel = {}
    mutex_gp.acquire()
    for column in authorized_personnel_df:
        try:
            if teams[column]:
                pass
        except KeyError:
            teams[column] = {}
        finally:
            for user in authorized_personnel_df[column]:
                if user:
                    try:
                        # Splits the string "User:XXXXXX"
                        user_name, user_id = user.split(":")

                        if user_id not in teams[column]:
                            # Tries to send a message, in order to verify the existence of the chat_id
                            notification = "You've been added to the Bot's authorized personnel\nTeam:    {}".format(column)
                            send(user_id, notification, type='message')
                            # If the message goes through, adds the administrator to the dictionary
                            authorized_personnel[user_id] = user_name
                            teams[column][user_id] = user_name
                        else:
                            authorized_personnel[user_id] = user_name
                            teams[column][user_id] = user_name

                    except telepot.exception.TelegramError:
                        # If an error occurs while adding the user to the dictionary, registers it to a log file
                        log("Telegram Error", "{while adding user to authorized_personnel. Probably chat_id does not exist.}", user)
                        continue
                    except ValueError:
                        log("Value Error", "{while adding a user to authorized_personnel. Probably string was formatted wrong.}", user)
                        continue
            # Case the users are not registered in the file but their ID is in the Dictionary
            # Removes the faulty users
            to_pop = []
            for chat_id, name in teams[column].items():
                if name+":"+chat_id not in authorized_personnel_df[column].to_numpy():
                    to_pop.append(chat_id)
            for chat_id in to_pop:
                teams[column].pop(chat_id)
            to_pop.clear()
    mutex_gp.release()


# TODO: ADD RETURN ANSWER
def add_user_team(string, adm):
    global authorized_personnel
    # reads authorized_personnel.csv
    authorized_personnel_df = pandas.read_csv("authorized_personnel.csv")
    # splits the string
    string = string.split(" ")
    # First item is Team name, after that users
    team_name = string.pop(0)
    string.append(adm)
    # Verifies if group already exists
    if team_name in authorized_personnel_df:
        answer = str(team_name) + " team already exists"
        return answer

    team_members = string
    # Adds users to authorized personnel
    for user in team_members:
        name, chat_id = user.split(":")
        authorized_personnel[chat_id] = name
    new_df = pandas.DataFrame({team_name: team_members})

    authorized_personnel_df = authorized_personnel_df.append(new_df, sort=False).reset_index(drop=True)
    authorized_personnel_df = authorized_personnel_df.append({'TeamADM': adm}, sort=False, ignore_index=True).reset_index(drop=True)

    authorized_personnel_df[team_name] = authorized_personnel_df[team_name].drop_duplicates().sort_values().reset_index(drop=True)
    authorized_personnel_df['TeamADM'] = authorized_personnel_df['TeamADM'].drop_duplicates().sort_values().reset_index(drop=True)

    authorized_personnel_df.to_csv("authorized_personnel.csv", index=False)
    update_personnel()
    answer = "Team added successfully"
    return answer


def add_user(team_user_list):
    # Adds a list of chat_id to authorized personnel csv file
    # Team_user_list = Team Name:XXXXXX Name:YYYYYYY Name:ZZZZZZZ

    # Splits the string into a list
    team_user_list = team_user_list.split(" ")
    # Defines the team as the first item of the list
    team = team_user_list.pop(0)
    # Verifies if Group name is valid
    mutex_gp.acquire()
    if team in teams:
        user_list = team_user_list
        # Reads authorized_personnel.csv file
        authorized_personnel_df = pandas.read_csv('authorized_personnel.csv')
        # Turns the user_list info into a DataFrame
        new_users_df = pandas.DataFrame(user_list, columns=[team])
        # Appends the users DataFrame into the authorized_personnel_df and organizes it
        authorized_personnel_df = authorized_personnel_df.append(new_users_df, sort=False).reset_index(drop=True)
        authorized_personnel_df[team] = authorized_personnel_df[team].drop_duplicates().sort_values().reset_index(drop=True)
        # Writes over authorized_personnel.csv with new user added
        authorized_personnel_df.to_csv('authorized_personnel.csv', index=False)
        mutex_gp.release()
        update_personnel()
    else:
        log("Inconsistency", "[tried to add a users to an invalid team]", team)


def remove_user(user_list, to_pop_team=None):
    # Removes a user from authorized personnel csv file
    # User_list = XXXXXX YYYYYYY ZZZZZZZ

    global authorized_personnel, teams
    if to_pop_team == 'ALL':
        to_pop_team = None
    # Splits the string into a list
    user_list = user_list.split(" ")
    # Imports authorized_personnel_df
    authorized_personnel_df = pandas.read_csv('authorized_personnel.csv')
    # Removes each user of the list
    mutex_PV.acquire()
    mutex_gp.acquire()
    mutex_user.acquire()
    for user_id in user_list:
        try:
            # Verifies if user exists in authorized personnel dictionary
            if user_id in authorized_personnel:
                if to_pop_team and user_id in teams[to_pop_team]:
                    user = teams[to_pop_team].pop(user_id) + ":" + user_id
                    # If exists, tries to send a message informing the Id is no longer authorized
                    send(user_id, "You've been removed from [{}] Team".format(to_pop_team), type='message')
                    # Removes the ID from the DataFrame
                    authorized_personnel_df[to_pop_team] = authorized_personnel_df[to_pop_team].replace(user, float('NaN'))
                    log("User removed", user=user)
                    # Verifies if user is still registered in any Team
                    still_authorized = False
                    for user_team, chat_ids in teams.items():
                        if user_id in chat_ids:
                            still_authorized = True
                    # If user isn't registered to any team, removes from authorized personnel and PV_mon
                    if not still_authorized:
                        authorized_personnel.pop(user_id)
                        mutex_PV.release()
                        mutex_gp.release()
                        unsubscribe('ALL', user)
                        mutex_PV.acquire()
                        mutex_gp.acquire()
                elif not to_pop_team:
                    user = authorized_personnel.pop(user_id) + ":" + user_id
                    for team, users in teams.items():
                        if user_id in users:
                            users.pop(user_id)
                    # If exists, tries to send a message informing the Id is no longer authorized
                    send(user_id, "You've been removed from the Bot's authorized personnel", type='message')
                    # Removes the ID from the DataFrame
                    authorized_personnel_df = authorized_personnel_df.replace(user, float('NaN'))
                    # Unsubscribes user from PV monitor
                    mutex_PV.release()
                    mutex_gp.release()
                    unsubscribe('ALL', user)
                    mutex_PV.acquire()
                    mutex_gp.acquire()
                    log("User removed", user=user)
                else:
                    continue
            # If the ID does not exist in  any authorized personnel dictionary registers a log message
            else:
                log("Inconsistency", "[tried to remove a user that does not exist. Probably string was formatted wrong]", user_id)
        # If it fails to send a Message
        except telepot.exception.TelegramError:
            log("Telegram Error", "{while removing a user. Probably chat_id does not exist.}", user_id)
            continue
        # If it fails to split the string
        except ValueError:
            log("Value Error", "{while removing a user. Probably string was formatted wrong.}", user_id)
            continue
    # Organizes the columns alphabetically
    for column in authorized_personnel_df:
        authorized_personnel_df[column] = authorized_personnel_df[column].sort_values().reset_index(drop=True)
    # Writes over authorized_personnel.csv with new DataFrame
    authorized_personnel_df.to_csv('authorized_personnel.csv', index=False)
    mutex_PV.release()
    mutex_gp.release()
    mutex_user.release()
    update_personnel()


def update_PV_groups():
    # Imports PV Groups that were registered

    global PV_groups
    mutex_PV.acquire()
    groups_df = pandas.read_csv("groups.csv", keep_default_na=False)
    # PV names
    pvs = groups_df["PVs"]
    # PV groups
    group = groups_df["Group"]
    # Standard limits
    std_max = groups_df["StdMax"]
    std_min = groups_df["StdMin"]
    std_timeout = groups_df["StdTimeout"]
    # Dictionary with all PV groups as keys and PV names and limits as values
    PV_groups = {}
    for i in range(len(group)):
        if not group[i]:
            continue
        # Dictionary with PV names as keys and a list with maximum and minimums as value
        pv_group_info = {}
        pv_name = pvs[i].split(";")
        pv_max = std_max[i].split(";")
        pv_min = std_min[i].split(";")
        timeout = std_timeout[i]
        # Adds keys and values to pv_group_info dictionary
        pv_group_info['timeout'] = timeout
        for name in pv_name:
            pv = epics.PV(name)
            time.sleep(0.1)
            pv_is_connected = pv.connect()
            time.sleep(0.1)
            if pv_is_connected:
                pv_group_info[name] = [pv_max[pv_name.index(name)], pv_min[pv_name.index(name)]]
                pv.disconnect()
            else:
                log("Disconnected PV", "{probably PV name  is wrong}", name)
        # Adds the group's info to PV_groups
        PV_groups[group[i]] = pv_group_info
    mutex_PV.release()

# Result:
# PV_groups[group] = {'PV_name_1' : ['std_max_value_1', 'std_min_value_1'],
#                       'PV_name_2' : ['std_max_value_2', 'std_min_value_2']}
# Example:
# PV_groups[Controle] = {'CON:MBTemp:Ch1' : ['100','0'],
#                           'CON:MBTemp:Ch2' : ['50','25']}


def update_PV_values():
    # Adds PVs that are going to be monitored to a dictionary with their values

    global PV_groups, PV_values, PV_mon
    mutex_PV.acquire()
    for group, pvs in PV_groups.items():
        try:
            # Verifies if group already exists
            if PV_mon[group]:
                for pv_name in pvs:
                    if pv_name == "timeout":
                        continue
                    try:
                        # Verifies if PV already exists in this group
                        if PV_mon[group][pv_name]:
                            pass
                    # Case PV does not exist in this group adds to it
                    except KeyError:
                        PV_values[pv_name] = epics.PV(pv_name)
                        PV_mon[group][pv_name] = {}
                        continue
        # Case the group does not exist adds group
        except KeyError:
            PV_mon[group] = {}
            for pv_name in pvs:
                if pv_name == 'timeout':
                    continue
                PV_values[pv_name] = epics.PV(pv_name)
                PV_mon[group][pv_name] = {}
            continue
    mutex_PV.release()

# Result:
# PV_values = {'PV_name_1' : value_1, 'PV_name_2' : value_2}
# Example:
# PV_values = {'CON:MBTemp:Ch1' : 27, 'CON:MBTemp:Ch2' : 26}


def update_PV_mon():
    # Updates dictionary that contains the monitoring information for every Process Variable

    global PV_mon
    mutex_PV.acquire()
    mutex_gp.acquire()
    # Copies the PVs from groups.csv to monitor_info.csv
    groups_df = pandas.read_csv("groups.csv", keep_default_na=False)
    # PV names
    pvs = groups_df["PVs"]

    # PV groups
    group = groups_df["Group"]
    # Standard limits
    std_max = groups_df["StdMax"]
    std_min = groups_df["StdMin"]
    std_timeout = groups_df["StdTimeout"]
    # In order to import the same PV in multiple groups we have to break the Dictionary pattern
    # Therefore creating a list of dicts instead of a dict of dicts
    groupscsv_to_monitorcsv = []

    for i in range(len(group)):
        # Turning the cell strings into lists
        pv_name = pvs[i].split(";")
        pv_max = std_max[i].split(";")
        pv_min = std_min[i].split(";")

        # Adding said strings to the list of dicts
        for pv in pv_name:
            index_1 = pv_name.index(pv)
            groupscsv_to_monitorcsv.append({"PVNames": pv, "PVGroups": group[i], "Max": pv_max[index_1],
                                            "Min": pv_min[index_1], "Timeout": std_timeout[i]})

    df = pandas.DataFrame(groupscsv_to_monitorcsv).sort_values(by=['PVGroups']).reset_index(drop=True)
    # Copies the PVs from groups.csv to monitor_info.csv
    mutex_csv.acquire()
    monitor_info_df = pandas.read_csv("monitor_info.csv", keep_default_na=False)
    monitor_info_df = monitor_info_df.append(df, sort=False).drop_duplicates(subset=['PVNames', 'PVGroups'], keep='first').sort_values(by=['PVGroups']).reset_index(drop=True)
    # Guarantees user is subscribed to every PV in every PV group
    # Reindex axis
    monitor_info_df = monitor_info_df.set_index(['PVGroups', 'PVNames'])
    # Subscribes users already subscribed to PVs that were added to a group
    for group, pvs in PV_groups.items():
        users_subscribed = False
        for pv in pvs:
            if pv == 'timeout':
                continue
            if monitor_info_df['ChatIDs'][group][pv] not in ['', 'NaN', float('NaN')]:
                users_subscribed = True
                users = monitor_info_df['ChatIDs'][group][pv]
                break
        if users_subscribed:
            for pv in pvs:
                monitor_info_df['ChatIDs'][group][pv] = users
    monitor_info_df = monitor_info_df.swaplevel().reset_index()
    monitor_info_df.to_csv("monitor_info.csv", index=False)
    # Imports the updated csv file as a DataFrame with multiple Indexes:
    # PVGroups and PVNames, to avoid problems with same PVs belonging to different groups
    monitor_info_df = pandas.read_csv("monitor_info.csv", keep_default_na=False, index_col=[1, 0])
    mutex_csv.release()
    # Importing DataFrame columns
    chat_id_column = monitor_info_df["ChatIDs"]
    max_column = monitor_info_df["Max"]
    min_column = monitor_info_df["Min"]
    timeout_column = monitor_info_df["Timeout"]

    # Using all_groups dict we have access to the PVGroups and the PVNames
    for gp, collection in PV_groups.items():
        for pv, info in collection.items():

            if pv == "timeout":
                continue
            pv_ids = chat_id_column[gp][pv].split(";")
            pv_max = str(max_column[gp][pv])
            pv_min = str(min_column[gp][pv])
            # Uncomment for different limits for users
            # pv_max = str(max_column[gp][pv]).split(";")
            # pv_min = str(min_column[gp][pv]).split(";")
            # Checks if there is any chat_id subscribed to this PV
            if chat_id_column[gp][pv]:

                for i in range(len(pv_ids)):
                    if pv_ids[i] in PV_mon[gp][pv]:
                        PV_mon[gp][pv][pv_ids[i]]['max'] = pv_max
                        PV_mon[gp][pv][pv_ids[i]]['min'] = pv_min
                        PV_mon[gp][pv][pv_ids[i]]['timeout'] = collection['timeout']
                        # Uncomment for different limits for users
                        # PV_mon[gp][pv][pv_ids[i]]['max'] = pv_max[i]
                        # PV_mon[gp][pv][pv_ids[i]]['min'] = pv_min[i]
                        # PV_mon[gp][pv][pv_ids[i]]['timeout'] = collection['timeout']
                        continue
                    now_time = time.time()
                    PV_mon[gp][pv][pv_ids[i]] = {"max": pv_max, "min": pv_min, "timeout": collection['timeout'],
                                                 "max_bool": False, "tmax": now_time, "min_bool": False, "tmin": now_time}
                    # Uncomment for different limits for users
                    # PV_mon[gp][pv][pv_ids[i]] = {"max": pv_max[i], "min": pv_min[i], "timeout": collection['timeout'],
                    #                              "max_bool": False, "tmax": now_time, "min_bool": False, "tmin": now_time}

            # Removing users from dictionary case they are no longer registered in the file
            to_pop = []
            for previous_id in PV_mon[gp][pv]:
                if previous_id not in pv_ids:
                    to_pop.append(previous_id)
            for chat_id in to_pop:
                PV_mon[gp][pv].pop(chat_id)
            to_pop.clear()
    mutex_PV.release()
    mutex_gp.release()

# Result:
# PV_mon = {'Group': {'PV_name_1': {'ID_1:XXXXXXXX':
#                                  {'max': X, 'min': Y, 'timeout': Z, 'max_bool': True/False, 'min_bool': True/False}}}}
# Example:
# PV_mon = {'Klystron1': {'K1Temp1': {'Patricia:XXXXXXXX':
#                                    {'max': '100', 'min': '0', 'timeout': 20, 'max_bool': False, 'min_bool': False},
#                                    'Vitor:YYYYYYYY':
#                                    {'max': '80', 'min': '40', 'timeout': 20, 'max_bool': True, 'min_bool': False}}}}


def monitor():
    # Monitors and notifies users about PV out of range, shall operate as Thread


    global PV_mon, PV_values
    # Unconditional loop for this Thread
    while True:
        mutex_PV.acquire()
        mutex_gp.acquire()
        # Defines the monitor time
        now_time = time.time()
        # Copies PV_mon in order to avoid Dictionary size changes during iteration
        PV_mon_copy = PV_mon.copy()
        # Repeats this for every PV group and every PV dictionary
        for group, pvs in PV_mon_copy.items():
            PV_mon_copy[group] = pvs.copy()
            for pv, chat_ids in PV_mon_copy[group].items():
                # Case no user is subscribed for this group, breaks and continues for next group
                if not chat_ids:
                    break
                # try:
                # Verifies if the PV is between the limits established for each user
                PV_mon_copy[group][pv] = chat_ids.copy()
                for user, info in PV_mon_copy[group][pv].items():

                    # Creates boolean variables to verify if PV is in between it's limits
                    value = PV_values[pv].value
                    greater_than_limit = float(value) > float(info['max'])
                    lesser_than_limit = float(value) < float(info['min'])
                    # Case PV is greater than it's limit
                    if greater_than_limit:
                        # print(info['timeout'])
                        # Defines boolean variables to verify if it's been greater than it's limit for
                        # the time in minutes specified for this user
                        time_max_out = (now_time - float(info['tmax']) >= (float(info['timeout'])*60))
                        # Case it's the PV's first time exceeding it's limits. Resets the timer and notifies user
                        if not info['max_bool']:
                            info['max_bool'] = True
                            info['tmax'] = now_time
                            log("Warning", "{exceeded its maximum limit for user: " + user + "}", pv)
                            warning_message = """
***WARNING***
A Process Variable has exceeded it's maximum limits
Group:   {}
PV:      {}
Value:   {}
Limit:   {}""".format(group, pv, value, info['max'])
                            # Verifies if user is actually an entire Team
                            if user in teams:
                                for chat_id, name in teams[user].items():
                                    # Verifies if chat_id is not a group chat
                                    if int(chat_id) > 0:
                                        send(chat_id, warning_message, type='message')
                            # case user isn't an entire Team
                            else:
                                chat_id = user.split(":")[1]
                                send(chat_id, warning_message, type='message')
                        # Case it isn't the PV's first time exceeding it's limits and time_max_out is True.
                        # Resets the timer and notifies user
                        elif time_max_out:
                            info['tmax'] = now_time
                            log("Warning", "{exceeded its maximum limit for user: " + user + "}", pv)
                            warning_message = """
***WARNING***
A Process Variable has exceeded it's maximum limits
Group:   {}
PV:      {}
Value:   {}
Limit:   {}""".format(group, pv, value, info['max'])
                            # Verifies if user is actually an entire Team
                            if user in teams:
                                for chat_id, name in teams[user].items():
                                    # Verifies if chat_id is not a group chat
                                    if int(chat_id) > 0:
                                        send(chat_id, warning_message, type='message')
                            # case user isn't an entire Team
                            else:
                                chat_id = user.split(":")[1]
                                send(chat_id, warning_message, type='message')
                    # Case PV is not greater than it's limit
                    else:
                        info['max_bool'] = False
                        info['tmax'] = now_time

                    # Case PV is lesser than it's limit
                    if lesser_than_limit:
                        # Defines boolean variables to verify if it's been lesser than it's limit for
                        # the time in minutes specified for this user
                        time_min_out = (now_time - float(info['tmin']) >= float(info['timeout'])*60)
                        # Case it's the PV's first time exceeding it's limits. Resets the timer and notifies user
                        if not info['min_bool']:
                            # print("first")
                            info['min_bool'] = True
                            info['tmin'] = now_time
                            log("Warning", "{exceeded its minimum limit for user: " + user + "}", pv)
                            warning_message = """
***WARNING***
A Process Variable has exceeded it's minimum limits
Group:   {}
PV:      {}
Value:   {}
Limit:   {}""".format(group, pv, value, info['min'])
                            # Verifies if user is actually an entire Team
                            # Not being used
                            if user in teams:
                                for chat_id, name in teams[user].items():
                                    # Verifies if chat_id is not a group chat
                                    if int(chat_id) > 0:
                                        send(chat_id, warning_message, type='message')
                            # case user isn't an entire Team
                            else:
                                chat_id = user.split(":")[1]
                                send(chat_id, warning_message, type='message')
                        # Case it isn't the PV's first time exceeding it's limits and time_max_out is True.
                        # Resets the timer and notifies user
                        elif time_min_out:
                            # print("retriggered")
                            info['tmin'] = now_time
                            log("Warning", "{exceeded its minimum limit for user: " + user + "}", pv)
                            warning_message = """
***WARNING***
A Process Variable has exceeded it's minimum limits
Group:   {}
PV:      {}
Value:   {}
Limit:   {}""".format(group, pv, value, info['min'])
                            # Verifies if user is actually an entire Team
                            if user in teams:
                                for chat_id, name in teams[user].items():
                                    # Verifies if chat_id is not a group chat
                                    if int(chat_id) > 0:
                                        send(chat_id, warning_message, type='message')
                            # case user isn't an entire Team
                            else:
                                chat_id = user.split(":")[1]
                                send(chat_id, warning_message, type='message')
                    # Case PV is not lesser than it's limit
                    else:
                        info['min_bool'] = False
                        info['tmin'] = now_time
        mutex_gp.release()
        mutex_PV.release()
        time.sleep(0.1)


def add_group(group_str):
    # Adds a PVGroup to groups.csv file

    global PV_groups
    groups_df = pandas.read_csv("groups.csv", keep_default_na=False)
    # Splits the string into a list
    to_add_list = group_str.split(" ")
    # Takes out the first item of the list, the name of the group to be added
    to_add_group = to_add_list.pop(0)
    if to_add_group in PV_groups:
        log("Name Error", "{while adding a new group. Group name already exists: [" + to_add_group + "] }")
        return False
    to_add_timeout = to_add_list.pop(len(to_add_list)-1)
    minimum = to_add_list.pop(len(to_add_list)-1)
    maximum = to_add_list.pop(len(to_add_list)-1)
    try:
        to_add_timeout = float(to_add_timeout)
        float(maximum)
        float(minimum)
    except ValueError:
        log("Value Error", "{while adding a new group, probably string was formatted wrong}")
        return False
    # Verify if maximum and minimum limits are valid
    if float(minimum) > float(maximum):
        log("Value Error", "{while adding a new group, minimum value is greater than maximum value}")
        return False
    # Adds the same limits to every PV in a group
    to_add_max = []
    to_add_min = []
    for pv_name in to_add_list:
        pv = epics.PV(pv_name)
        time.sleep(0.1)
        true = pv.connect()
        time.sleep(0.1)
        if true:
            to_add_max.append(maximum)
            to_add_min.append(minimum)
            pv.disconnect()
        else:
            to_add_list.pop(to_add_list.index(pv_name))

    if not to_add_list:
        log("Error", "{while adding a new PV Group, no valid PVs where provided}")
        return False
    # Joins the remaining items (PVnames) into a string
    to_add_pvs = ";".join(to_add_list)

    # Formats the maximum and minimum list to strings so they can them be added to a pandas.Series
    to_add_max = ";".join(to_add_max)
    to_add_min = ";".join(to_add_min)
    # Creates the list that is going to be added
    to_add = pandas.Series({"Group": to_add_group, "PVs": to_add_pvs, "StdMax": to_add_max, "StdMin": to_add_min,
                            "StdTimeout": to_add_timeout})
    groups_df = groups_df.append(to_add, ignore_index=True, sort=True).drop_duplicates()
    # Writes over groups.csv with new DataFrame
    groups_df.to_csv('groups.csv', index=False)
    log("New PVGroup added", "[" + to_add_group + "]", "Group Name")
    update_PV_groups()
    update_PV_values()
    update_PV_mon()
    return True


def remove_group(group_str):
    # Removes PV Groups that are not being used

    global PV_groups, PV_mon, PV_values, mutex_gp, mutex_PV
    # Imports groups csv and monitor_info csv
    groups_df = pandas.read_csv("groups.csv", keep_default_na=False, index_col=[0])
    mutex_csv.acquire()
    monitor_info_df = pandas.read_csv("monitor_info.csv", keep_default_na=False, index_col=[0, 1])
    to_pop_list = group_str.split(" ")
    # logs request
    log("Remove PVGroup request", "{administrator wishes to remove the following PVGroups}", "{}".format(to_pop_list))
    # waits for monitor loop to stop
    mutex_gp.acquire()
    mutex_PV.acquire()
    # Strings to be returned
    errors = ''
    answer = ''
    # list that will contain the PVs from the removed groups
    to_pop_pv_list = []
    for to_pop_group in to_pop_list:
        # verifies if group name is registered in PV_mon
        if to_pop_group in PV_mon:
            keep_group = False
            for group, pvs in PV_mon.items():
                # verifies if group is in the list of groups to be removed
                if group == to_pop_group:
                    # verifies if there is any user subscribed to this PV group
                    user_sub = False
                    for pv, chat_ids in pvs.items():
                        to_pop_pv_list.append(pv)
                        if chat_ids:
                            user_sub = True
                    # if no user is subscribed remove PV Group
                    if not user_sub:
                        monitor_info_df = monitor_info_df.drop(to_pop_group, level=1)
                        groups_df = groups_df.drop(to_pop_group)
                        PV_groups.pop(to_pop_group)
                        answer += "\n[{}] PV Group has been removed" .format(to_pop_group)
                        log("PVGroup removed", to_pop_group)
                    # if there is any user subscribed warns administrator
                    else:
                        errors += "\n[{}] PV Group has users subscribed" .format(to_pop_group)
                        keep_group = True
                        log("PVGroup remove failed", "{there are users subscribed to the PV group}", to_pop_group)
            if not keep_group:
                PV_mon.pop(to_pop_group)
        else:
            errors += "\n[{}] PV Group isn't registered".format(to_pop_group)
            log("PVGroup remove failed", "{there is no such group in monitor_info.csv file}", to_pop_group)
    for pv in to_pop_pv_list:
        keep_pv = False
        for gp, pvs in PV_mon.items():
            if pv in pvs:
                keep_pv = True
        if not keep_pv:
            PV_values.pop(pv)
    mutex_PV.release()
    mutex_gp.release()
    monitor_info_df.to_csv("monitor_info.csv")
    muter_csv.release()
    groups_df.to_csv("groups.csv")
    # update all dictionaries after this
    return answer, errors


def add_pv_to_group(pv_string):
    # Adds a Process Variable to a Group that is already being monitored
    # Returns a string to answer the person who made the request

    global PV_groups
    pv_string = pv_string.split(" ")
    # Verifies if string is formatted correctly
    try:
        if len(pv_string) == 4:
            to_add_group = pv_string[0]

            # Verifies if group exists
            if to_add_group in PV_groups:

                # Prepares the variables to be added
                to_add_pv = pv_string[1]
                pv = epics.PV(to_add_pv)
                time.sleep(0.1)
                pv_is_connected = pv.connect()
                time.sleep(0.1)
                if not pv_is_connected:
                    log("Disconnected PV", "{while adding PV to group. Probably PV name  is wrong}", to_add_pv)
                    error = "[{}] process variable does not exist".format(to_add_pv)
                    return error
                to_add_max = pv_string[2]
                to_add_min = pv_string[3]

                # Testing if string was formatted correctly
                float(to_add_max)
                float(to_add_min)

                # Importing PVGroups df and it's columns
                groups_df = pandas.read_csv("groups.csv", keep_default_na=False, index_col=[0])
                pvs_column = groups_df["PVs"]
                max_column = groups_df["StdMax"]
                min_column = groups_df["StdMin"]

                # Verifies if PV already exists in the group
                if to_add_pv in pvs_column[to_add_group]:

                    # Finds where the PV information is located
                    pvs_list = pvs_column[to_add_group].split(";")
                    max_list = max_column[to_add_group].split(";")
                    min_list = min_column[to_add_group].split(";")
                    index = pvs_list.index(to_add_pv)
                    # Alters the PV limits
                    max_list[index] = to_add_max
                    min_list[index] = to_add_min
                    max_column[to_add_group] = ';'.join(max_list)
                    min_column[to_add_group] = ';'.join(min_list)
                    # Updates the dictionaries
                    groups_df.to_csv('groups.csv', index=True)
                    update_PV_groups()
                    update_PV_values()
                    update_PV_mon()
                    answer = """
PV Limits altered
PVGroup:   {}
PVName:    {}
Max:       {}
Min:       {}""".format(to_add_group, to_add_pv, to_add_max, to_add_min)
                    log("PV Limits altered", "{}: max = {}, min = {}".format(to_add_pv, to_add_max, to_add_min), to_add_group)
                    return answer

                # Case the PV doesn't exist in this group
                else:
                    # Includes the PV and it's limits to the groups cells
                    pvs_column[to_add_group] = str(pvs_column[to_add_group]) + ";" + str(to_add_pv)
                    max_column[to_add_group] = str(max_column[to_add_group]) + ";" + str(to_add_max)
                    min_column[to_add_group] = str(min_column[to_add_group]) + ";" + str(to_add_min)
                    # Updates the dictionaries
                    groups_df.to_csv('groups.csv', index=True)

                    update_PV_groups()
                    update_PV_values()
                    update_PV_mon()
                    # Answers the user and logs the information
                    answer = """
New Process Variable added.
PVGroup:   {}
PVName:    {}
Max:       {}
Min:       {}""".format(to_add_group, to_add_pv, to_add_max, to_add_min)
                    log("New Process Variable", "{}: max = {}, min = {}".format(to_add_pv, to_add_max, to_add_min), to_add_group)
                    return answer

            # Case the group is not registered
            else:
                answer = "Inconsistency. The specified group does not exist or isn't registered."
                log("Inconsistency", "[tried to add a Process variable to a group that does not exist: "+to_add_group+"]")
                return answer
        # Case the string was formatted wrong
        else:
            answer = """
Formatting Error. Format the message as follows:
/addpv (GroupName) (PVName) (MaxLimit) (MinLimit)"""
            log("Formatting Error", "{while adding Process Variable to PVGroup. Probably string was formatted wrong: "+str(pv_string)+"}")
            return answer
    # Case the limits were formatted wrong
    except ValueError:
        answer = """
Formatting Error. Format the message as follows:
/addpv (GroupName) (PVName) (MaxLimit) (MinLimit)"""
        log("Value Error", "{while adding PV to PVGroup. Probably string was formatted wrong}")
        return answer


# TODO: Add return Message
def set_timeout(timeout_string):
    # Sets the timeout of a group to the specified value
    global PV_groups
    try:
        pv_group, timeout = timeout_string.split(" ")
        timeout = float(timeout)
    # If the string contains more or less than two words
    except ValueError:
        log("ValueError", "{while adjusting timeout, probably string was not formatted correctly}")
        return "Error, string was not formatted correctly"
    # Verifies if PV group name is valid
    if pv_group not in PV_groups:
        log("Inconsistency", "{while adjusting timeout, specified PV group does not exist}")
        return "[{}] PV group does not exist".format(pv_group)
    groups_df = pandas.read_csv("groups.csv", keep_default_na=False, index_col=[0])
    groups_df["StdTimeout"][pv_group] = timeout
    groups_df.to_csv("groups.csv")
    update_PV_groups()
    update_PV_values()
    update_PV_mon()
    return "Timeout of [{}] PV Group successfully adjusted to {} minutes".format(pv_group, timeout)


def subscribe(desired_groups, user):
    # Adds a user to PV_mon

    # Imports all_goups dictionaries to verify existence of desired group
    global PV_groups
    # Imports monitor_info as DataFrame and it's columns
    mutex_csv.acquire()
    monitor_info_df = pandas.read_csv("monitor_info.csv", keep_default_na=False)
    groups_column = monitor_info_df["PVGroups"]
    chat_id_column = monitor_info_df["ChatIDs"]
    monitor_info_pvs = monitor_info_df["PVNames"]
    max_column = monitor_info_df["Max"]
    min_column = monitor_info_df["Min"]
    timeout_column = monitor_info_df["Timeout"]

    # Imports groups_df in order to add Standard Limits
    groups_df = pandas.read_csv("groups.csv", keep_default_na=False, index_col=[0])
    stdmax_column = groups_df["StdMax"]
    stdmin_column = groups_df["StdMin"]
    stdtimeout_column = groups_df["StdTimeout"]
    groups_df_pvs = groups_df["PVs"]

    # Turns desired groups string into a list
    log("Group subscription", "[wishes to subscribe to the following groups: "+str(desired_groups)+"]", user)
    if desired_groups == 'ALL':
        desired_groups = list(PV_groups.keys())
    elif type(desired_groups) == str:
        desired_groups = desired_groups.split(" ")
    # Errors string
    return_message = ""
    errors = ""
    # For loop to read every group cell in groups column
    for i in range(len(groups_column)):
        # For loop to go through every desired group
        for group in desired_groups:
            # Verifies if group name exists
            if group in PV_groups:
                # Verifies if the user is already subscribed to this Group
                if user in chat_id_column[i]:
                    pass

                # Verifies if the current group cell is this group's cell and if chat_id cell is not empty
                elif groups_column[i] == group and chat_id_column[i]:
                    # Checks which PV is being subscribed at the moment
                    pv_name = monitor_info_pvs[i]
                    # Extracts this PVs limits from groups_df
                    pv_list = groups_df_pvs[group].split(";")
                    index = pv_list.index(pv_name)
                    maximum = stdmax_column[group].split(";")[index]
                    minimum = stdmin_column[group].split(";")[index]
                    timeout = stdtimeout_column[group]
                    # Writes to monitor_df
                    chat_id_column[i] = chat_id_column[i] + ";" + user
                    max_column[i] = str(maximum)
                    min_column[i] = str(minimum)
                    # Uncomment for different limits
                    # max_column[i] = str(max_column[i]) + ";" + str(maximum)
                    # min_column[i] = str(min_column[i]) + ";" + str(minimum)
                    timeout_column[i] = str(timeout_column[i])
                    if "You have been added to [{}] PV Group".format(group) in return_message:
                        continue
                    return_message += "\nYou have been added to [{}] PV Group".format(group)

                # Case the chat_id cell is empty
                elif groups_column[i] == group:
                    # Checks which PV is being subscribed at the moment
                    pv_name = monitor_info_pvs[i]
                    chat_id_column[i] = user
                    # Extracts this PVs limits from groups_df
                    pv_list = groups_df_pvs[group].split(";")
                    index = pv_list.index(pv_name)
                    max_column[i] = stdmax_column[group].split(";")[index]
                    min_column[i] = stdmin_column[group].split(";")[index]
                    timeout_column[i] = str(stdtimeout_column[group])
                    if "You have been added to [{}] PV Group".format(group) in return_message:
                        continue
                    return_message += "\nYou have been added to [{}] PV Group".format(group)
            # Case the group's name is not registered
            elif not group:
                errors = "Please specify a PVGroup"
                log("Inconsistency", "[did not specify a PVGroup]", user)
            else:
                if "[{}] PV Group does not exist or isn't registered".format(group) in errors:
                    pass
                else:
                    errors += "\n[{}] PV Group does not exist or isn't registered".format(group)
                    log("Inconsistency", "[tried to subscribe to a group that does not exist: " + group + "]", user)
    # Pushes the changes to monitor_info.csv file
    if not return_message and not errors:
        errors = "Looks like you are already subscribed to the specified groups {}" .format(desired_groups)
    monitor_info_df["ChatIDs"] = chat_id_column
    monitor_info_df.to_csv("monitor_info.csv", index=False)
    mutex_csv.release()
    update_PV_mon()
    return return_message, errors


def unsubscribe(desired_groups, user):
    # Removes a user from PV_mon

    global PV_groups
    # Imports monitor info DataFrame
    mutex_csv.acquire()
    monitor_info_df = pandas.read_csv("monitor_info.csv", keep_default_na=False)
    groups_column = monitor_info_df["PVGroups"]
    chat_id_column = monitor_info_df["ChatIDs"]
    max_column = monitor_info_df["Max"]
    min_column = monitor_info_df["Min"]

    log("Group unsubscription", "[wishes to unsubscribe from the following groups: "+desired_groups+"]", user)

    if desired_groups == "ALL":
        desired_groups = list(PV_groups.keys())
    elif type(desired_groups) == str:
        desired_groups = desired_groups.split(" ")
    answer = ""
    errors = ""
    for group in desired_groups:
        # verifies if group name exists
        if group in PV_groups:
            # Removing user from csv file
            for i in range(len(groups_column)):
                # verifies if current cell is from the desired group
                if groups_column[i] == group:
                    # verifies if user is subscribed to the group
                    if user in chat_id_column[i]:
                        chat_id_cell = chat_id_column[i].split(";")

                        # Uncomment for different limits for users
                        # max_cell = str(max_column[i]).split(";")
                        # min_cell = str(min_column[i]).split(";")

                        # identifies the user position in the string
                        index_0 = chat_id_cell.index(user)
                        # Removes chat_id, max limit and min limit
                        chat_id_cell.pop(index_0)

                        # Uncomment for different limits for users
                        # max_cell.pop(index_0)
                        # min_cell.pop(index_0)

                        chat_id_column[i] = ";".join(chat_id_cell)
                        # Uncomment for different limits for users
                        # max_column[i] = ";".join(max_cell)
                        # min_column[i] = ";".join(min_cell)

                        if "You have been removed from [{}] PVGroup".format(group) not in answer:
                            answer += "\nYou have been removed from [{}] PVGroup".format(group)
        elif not group:
            errors = "Please specify a PVGroup"
            log("Inconsistency", "[did not specify a PVGroup to be unsubscribed]", user)

        else:
            errors += "\n[{}] is not a valid PVGroup".format(group)
            log("Inconsistency", "[tried to unsubscribe from a group that does not exist: " + group + "]", user)

    # Pushes changes to CSV file
    monitor_info_df.to_csv("monitor_info.csv", index=False)
    mutex_csv.release()
    update_PV_mon()
    return answer, errors


def action(msg):
    # Function to process received messages
    # try:

        valid_commands_str = """
/help - show bot functions
/caget (PVs) - get Process Variables values
/pvgroups - sends a list with registered PVGroups names
/pvgroupsfile - sends a CSV file with the registered PVGroups and the corresponding PVs
/subscribe (PVGroups) - subscribes you to the requested PVGroups (Individual users only)
/unsubscribe (PVGroups) - cancels subscription to the requested PVGroups
/checkme - returns your information
/checkgp (PV Groups) - returns PV Groups' information
/add (Team) (Username:ChatID) - requests administrators to add multiple users to a authorized personnel
/addteam (AdminName:AdminID) (Team) (Users) - requests administrators to register a new Team
/addpvgroup (Group) (PVs) (Maximum limit) (Minimum limit) (Timeout) - requests administrators to register a new PV Group
/addpv (Group) (PV) (Maximum limit) (Minimum limit) - requests administrators to register a new PV to an existing PV Group or alter a PV Limit
/forward (Message) - forwards the specified message to BOT administrators
/isalive - informs if monitoring is enabled
/getstatus (PVs) - gets status and archiving information for PVs (supports filters)"""
        team_adm_commands = """

Team Administrator commands:
/subscribeteam (Team) (PVGroups) - subscribes the Team you administrate to the requested PVGroups
/unsubscribeteam (Team) (PVGroups) - unsubscribes the Team you administrate from the requested PVGroups
/teams - sends a list with registered Teams
/getids (Teams) - returns a list with the names and ChatIDs from the specified Teams
/remove (Team) (ChatIDs) - removes the specified users from your Team
"""
        bot_adm_commands = """

BOT Administrator commands:
/teams - sends a list with registered Teams
/getids (Teams) - sends a list with the names and ChatIDs from the specified Teams
/subscribeteam (Team) (PVGroups) - subscribes the desired Team to the requested PVGroups
/unsubscribeteam (Team) (PVGroups) - unsubscribes the desired Team from the requested PVGroups
/removepvgroup (PVGroups) - removes PV Groups that are not being used from dictionaries and csv files
/remove (Team) (ChatIDs) - removes the specified users from the Team
/forward (ChatID) (Message) - forwards a message to the desired ChatID
/settimeout (PVGroup) (Timeout) - alters a PVGroup's notification timeout
/update - updates all dictionaries, use if you change any .csv file manually
"""
        # Imports authorized personnel dictionaries
        global authorized_personnel
        global PV_groups

        # Defines chat information
        chat_id = msg['chat']['id']
        chat_type = msg['chat']['type']
        if chat_type == "private":
            username = msg['chat']['first_name']
        elif chat_type == "group" or chat_type == "supergroup":
            username = msg['chat']['title']
        else:
            username = "NUoG"   # Neither User or Group
        user = username + ":" + str(chat_id)
        timestamp = msg['date']

        # Verifies if chat_id is authorized to use the Bot
        if str(chat_id) in authorized_personnel:
            # Verifies if the message sent is a valid command
            if "text" in msg:
                # Registers message to log file
                command = msg['text']
                log("New Message", command, user, timestamp=timestamp)

                # Bot information
                if command in ["/start", "/help"]:
                    # Bot information for Team Administrators
                    if str(chat_id) in teams['TeamADM']:
                        valid_commands_str += team_adm_commands
                    # Bot information for Bot administrators
                    if str(chat_id) in teams['ADM']:
                        valid_commands_str += bot_adm_commands
                    answer = """
Hello there, {}! Welcome to Controls Group new PV info Bot!
Here are my valid commands:{}


For more information check Wiki-Sirius page:  https://bit.ly/3fUH29v

To report bugs or errors answer this form:  https://bit.ly/3eDwLxW""".format(username, valid_commands_str)
                    send(chat_id, answer, type='message', disable_web_page_preview=True)

                # Requesting PV values
                elif command[:7] == "/caget ":
                    # Splits the PV arguments into a list
                    desired_PVs = command[7:].split(" ")
                    answer = ""
                    # Gets PV values for the PV list provided
                    for PV in desired_PVs:
                        if PV:
                            pv = epics.PV(PV)
                            answer += "\n{}: {}{}".format(PV, pv.value, pv.units)
                        # If user does not provide any PV
                        else:
                            answer += "Invalid arguments\nPlease specify the desired Process Variables"
                            log("Inconsistency", "[didn't specify a Process Variable] " + command, user, timestamp=timestamp)
                    send(chat_id, answer, type='message')

                # Answers the existing PVGroups
                elif command == "/pvgroups":
                    answer = "The existing PV groups are:"
                    group_list = []
                    for group in PV_groups:
                        group_list.append(group)
                    group_list.sort()
                    for group in group_list:
                        answer += "\n" + group
                    send(chat_id, answer, type='message')

                # Sends the group file so the user can check if the desired group already exists.
                elif command == "/pvgroupsfile":
                    file = open("groups.csv", 'r')
                    caption = "PVGroups file"
                    telegram_bot.sendDocument(chat_id, document=file, caption=caption)

                # Subscribing to a PV group, answers if PVGroup does not exist
                elif command[:11] == "/subscribe " and chat_type not in ["group", "supergroup"]:
                    desired_groups = command[11:]
                    answer, errors = subscribe(desired_groups, user)
                    send(chat_id, answer + errors, type='message')

                # Unsubscribing to PV groups
                elif command[:13] == "/unsubscribe " and chat_type not in ["group", "supergroup"]:
                    desired_groups = command[13:]
                    answer, errors = unsubscribe(desired_groups, user)
                    send(chat_id, answer + errors, type='message')

                # Rejects group chats that try to subscribe to a PVGroup
                elif command[:11] == "/subscribe ":
                    answer = "Sorry.\nGroup chats cannot subscribe to PV notifications due to Telegram's Spam policies."
                    log("Subscribe request rejected", "group chat tried to subscribe to a PV group", user, timestamp=timestamp)
                    send(chat_id, answer, type='message')

                # Subscribing entire Teams to a PV Group
                elif (command[:15] == "/subscribeteam " and
                      (str(chat_id) in teams['TeamADM'] or str(chat_id) in teams['ADM'])):
                    string = command[15:]
                    string = string.split(" ")
                    team = string.pop(0)
                    try:
                        # Verifies if user belongs to this team or if user is BOT administrator
                        if (str(chat_id) in teams[team] and team != "TeamADM" or
                                str(chat_id) in teams['ADM']):
                            desired_groups = " ".join(string)
                            answer, errors = subscribe(desired_groups, team)
                            if answer:
                                for individual_user in teams[team]:
                                    send(individual_user, answer, type='message')
                            # Informs the person who made the request whether errors occurred or not
                            if errors:
                                send(chat_id, errors, type='message')
                            elif str(chat_id) in teams['ADM']:
                                answer = "Successfully subscribed [{}] Team to the desired PV groups".format(team)
                                send(chat_id, answer, type='message')
                        # Case it has no domain over the group
                        else:
                            log("Subscribe Team Blocked", "administrator tried to subscribe a group that he doesn't belong", user, timestamp=timestamp)
                            answer = "You have no domain over [{}] Team".format(team)
                            send(chat_id, answer, type='message')
                    # Case an error occurs while verifying if the Team exists
                    except KeyError:
                        log("Key Error", "{while on subscribeteam, probably Team does not exist: " + command + "}", user, timestamp=timestamp)
                        error = "Please specify a valid Team"
                        send(chat_id, error, type='message')

                # Unsubscribing entire Teams from a PV Group
                elif (command[:17] == "/unsubscribeteam " and
                      (str(chat_id) in teams['TeamADM'] or str(chat_id) in teams['ADM'])):
                    string = command[17:].split(" ")
                    team = string.pop(0)
                    try:
                        # Verifies if user belongs to this Team or if user is BOT administrator
                        if (str(chat_id) in teams[team] and team != "TeamADM" or
                                str(chat_id) in teams['ADM']):
                            desired_groups = " ".join(string)
                            answer, errors = unsubscribe(desired_groups, team)
                            if answer:
                                for individual_user in teams[team]:
                                    send(individual_user, answer, type='message')
                            # Informs the person who made the request whether errors occurred or not
                            if errors:
                                send(chat_id, errors, type='message')
                            elif str(chat_id) in teams['ADM']:
                                answer = "Successfully unsubscribed [{}] Team from the desired PV groups".format(team)
                        # Case it has no domain over the Team
                        else:
                            log("Subscribe Team Blocked", "administrator tried to unsubscribe a Team that he doesn't belong", user, timestamp=timestamp)
                            answer = "You have no domain over [{}] Team".format(team)
                            send(chat_id, answer, type='message')
                    # Case an error occurs while verifying if the Team exists
                    except KeyError:
                        log("Key Error", "{while on unsubscribeteam, probably user group does not exist: " + command + "}", user, timestamp=timestamp)
                        error = "Please specify a valid TEam"
                        send(chat_id, error, type='message')

                # Requesting administrators to add people to authorized_personnel
                elif command[:5] == "/add " and str(chat_id) not in teams['ADM']:
                    log("Add user request", command, user, timestamp=timestamp)
                    forward_message = "[{}] wishes to add new authorized users:\n{}".format(user, command)
                    # Forwards the message for every administrator
                    for adm in teams['ADM']:
                        send(adm, forward_message, disable_notification=True, type='message')
                    answer = "Request forwarded to the Bot's administrators"
                    send(chat_id, answer, type='message')

                # Adding users to authorized personnel
                elif command[:5] == "/add ":
                    group_user_list = command[5:]
                    answer = "New ChatIDs added by [{}]:\n{}".format(user, group_user_list)
                    add_user(group_user_list)
                    # Informs administrators about the new users
                    for adm in teams['ADM']:
                        send(adm, answer, disable_notification=True, type='message')

                # Requesting administrators to add a new virtual group
                elif command[:9] == "/addteam " and str(chat_id) not in teams['ADM']:
                    log("Add user request", command, user, timestamp = timestamp)
                    forward_message = "[{}] wishes to add new Team:\n{}".format(user, command)
                    # Forwards the message for every administrator
                    for adm in teams['ADM']:
                        send(adm, forward_message, disable_notification=True, type='message')
                    answer = "Request forwarded to the Bot's administrators"
                    send(chat_id, answer, type='message')

                # Adds a new Team
                elif command[:9] == "/addteam ":
                    string = command[9:].split(" ")
                    team_adm = string.pop(0)
                    team_user_list = " ".join(string)
                    answer = add_user_team(team_user_list, team_adm)
                    if answer == "Team added successfully":
                        forward = "New Team added by [{}]:\n{} *{}*".format(user, team_user_list, team_adm)
                        send(chat_id, answer, type='message')
                        # Informs administrators about the new Team
                        for adm in teams['ADM']:
                            send(adm, forward, disable_notification=True, type='message')
                    else:
                        send(chat_id, answer, type='message')

                # Returns the chat ids from the Teams you want (for BOT ADMs and Team ADMs only)
                elif (command[:8] == "/getids " and
                      (str(chat_id) in teams['TeamADM'] or str(chat_id) in teams['ADM'])):
                    teams_str = command[8:]
                    teams_list = teams_str.split(" ")
                    answer = ""
                    for team in teams_list:
                        # Verifies if the team name exists
                        if team in teams:
                            users = ""
                            for c_id in teams[team]:
                                users += "{}:    {}\n".format(teams[team][c_id], c_id)
                            answer += "\n\n{}\n{}".format(team, users)
                        elif team:
                            answer += "\n\n[{}] does not exist".format(team)
                        else:
                            answer += "Please specify a team"
                    send(chat_id, answer, type='message')

                # Showing your information
                elif command == "/checkme":
                    user_teams = []
                    pv_groups = []
                    mutex_gp.acquire()
                    mutex_PV.acquire()
                    teams_copy = teams.copy()
                    for team in teams_copy:
                        if str(chat_id) in teams_copy[team]:
                            user_teams.append(team)
                    teams_copy.clear()
                    PV_mon_copy = PV_mon.copy()
                    for pv_group, pvs in PV_mon_copy.items():
                        PV_mon_copy[pv_group] = pvs.copy()
                        for pv_name, chatIDs in PV_mon_copy[pv_group].items():
                            if user in chatIDs.keys():
                                pv_groups.append(pv_group)
                                break
                            team_list = []
                            aux_bool = False
                            for team in user_teams:
                                if team in chatIDs.keys():
                                    team_list.append(team)
                                    aux_bool = True
                            if aux_bool:
                                team_list = ' '.join(team_list)
                                pv_groups.append(pv_group + "(" + team_list + ")")
                                break
                    mutex_gp.release()
                    mutex_PV.release()
                    user_teams = "   ".join(user_teams)
                    pv_groups = "   ".join(pv_groups)
                    answer = """
User Name:   {}
ChatID:   {}
Teams:   {}
PVGroups:   {}""" .format(username, chat_id, user_teams, pv_groups)
                    send(chat_id, answer, type='message')

                # Showing a PV Group information
                elif command[:9] == "/checkgp ":
                    gps = command[9:].split(" ")
                    mutex_gp.acquire()
                    mutex_PV.acquire()
                    answer = ""
                    for gp in gps:
                        if gp in PV_groups:
                            answer += gp + ":\n"
                            answer += "Timeout:  " + str(PV_groups[gp]['timeout']) + "min\n"
                            for pv, limits in PV_groups[gp].items():
                                if pv == 'timeout':
                                    continue
                                answer += "{} - Max:{} Min:{}\n".format(pv, limits[0], limits[1])
                            answer += "\n\n"
                    mutex_PV.release()
                    mutex_gp.release()
                    if answer:
                        send(chat_id, answer, type='message')
                    else:
                        error = "No valid group specified"
                        send(chat_id, error, type='message')

                # Showing existing Teams
                elif command == "/teams" and (str(chat_id) in teams['ADM'] or str(chat_id) in teams['TeamADM']):
                    answer = "The existing Teams are:"
                    team_list = []
                    for team in teams:
                        team_list.append(team)
                    team_list.sort()
                    for team in team_list:
                        answer += "\n" + team
                    send(chat_id, answer, type='message')

                # Removing users as Team administrator
                elif command[:8] == "/remove " and str(chat_id) in teams['TeamADM'] and str(chat_id) not in teams['ADM']:
                    user_list = command[8:].split(" ")
                    team = user_list[0]
                    try:
                        # Verifies if user is trying to remove from a team he doesn't belong or from "TeamADM"
                        if str(chat_id) not in teams[team] or team == "TeamADM":
                            log("Remove request rejected", "{user tried to remove from a Team he has no domain of: " + command + "}", user, timestamp=timestamp)
                            error = "You do not have domain over [{}] Team".format(team)
                            send(chat_id, error, type='message')
                        # Verifies if the first string is actually a Team
                        elif team in teams:
                            team = user_list.pop(0)
                            error = ""
                            for c_id in user_list:
                                # Removes the IDS that don't belong to the Team or were mistyped
                                if c_id not in teams[team]:
                                    error += "The ID [{}] is not in the Team\n" .format(c_id)
                                    user_list.pop(user_list.index(c_id))
                            # Informs the person who made the request about the errors
                            if error:
                                send(chat_id, error, type='message')
                            # If the list is not empty, removes the users
                            if user_list:
                                user_string = " ".join(user_list)
                                remove_user(user_string, team)
                                answer = "Users removed successfully"
                            # If list has no valid IDs
                            else:
                                answer = "No valid chatIDs specified"
                            send(chat_id, answer, type='message')

                        # Case the user is trying to remove from a Team that does not exist
                        else:
                            log("Remove request rejected", "{user tried to remove from a Team that does not exist: " + command + "}", user, timestamp = timestamp)
                            error = """
The Team [{}] does not exist, please format the message as follows:
/remove (Team) (chat_ids)""".format(team)
                            send(chat_id, error, type='message')
                    # Redundancy
                    except KeyError:
                        log("Remove request rejected", "{user tried to remove from a Team that does not exist: " + command + "}", user, timestamp=timestamp)
                        error = "The Team [{}] does not exist, please verify if you mistyped".format(team)
                        send(chat_id, error, type='message')

                # Removing users as BOT administrator
                elif command[:8] == "/remove " and str(chat_id) in teams['ADM']:
                    user_list = command[8:].split(" ")
                    team = user_list.pop(0)
                    # Verifies if administrator specified a Team
                    if team in teams or team == 'ALL':
                        error = ""
                        if team != 'ALL':
                            for c_id in user_list:
                                if c_id not in teams[team]:
                                    error += "The ID [{}] is not in the Team\n" .format(c_id)
                                    user_list.pop(user_list.index(c_id))
                        if error:
                            send(chat_id, error, type='message')
                        if user_list:
                            user_string = " ".join(user_list)
                            remove_user(user_string, team)
                            answer = "Users removed successfully"
                        else:
                            answer = "No valid users specified"
                        send(chat_id, answer, type='message')

                # Requesting administrators to register a new PV group
                elif command[:12] == "/addpvgroup " and str(chat_id) not in teams['ADM']:
                    log("Add PVGroup request", command, user, timestamp=timestamp)
                    forward_message = "[{}] wishes to add a new PV group:\n{}".format(user, command)
                    # Forwards the message for every administrator
                    for adm in teams['ADM']:
                        send(adm, forward_message, disable_notification=True, type='message')
                    answer = "Request forwarded to the Bot's administrators"
                    send(chat_id, answer, type='message')

                # Registering a new PV group
                elif command[:12] == "/addpvgroup ":
                    group_str = command[12:]
                    answer = add_group(group_str)
                    # Informs administrators about the new PVGroup
                    if answer:
                        group = group_str.split(" ")[0]
                        answer = "New PV Group added by {}: {}".format(username, group)
                        for adm in teams['ADM']:
                            send(adm, answer, type='message')
                    else:
                        error = "ERROR. Please verify if Group name already exists, if PVs are connected and if string was formatted correctly"
                        send(chat_id, error, type='message')

                # Removing PV groups
                elif command[:15] == "/removepvgroup " and str(chat_id) in teams['ADM']:
                    group = command[15:]
                    update_PV_groups()
                    update_personnel()
                    update_PV_values()
                    update_PV_mon()
                    answer, errors = remove_group(group)
                    update_PV_groups()
                    update_personnel()
                    update_PV_values()
                    update_PV_mon()
                    send(chat_id, answer + errors, type='message')

                # Requesting administrators to register a PV to an existing PV Group
                elif command[:7] == "/addpv " and str(chat_id) not in teams['ADM']:
                    forward_message = "[{}] wishes to add a new PV to an existing PV group:\n{}".format(user, command)
                    answer = "Request forwarded to the Bot's administrators"
                    send(chat_id, answer, type='message')
                    log("Add PV to Group request", command, user, timestamp=timestamp)
                    # Forwards the message for every administrator
                    for adm in teams['ADM']:
                        send(adm, forward_message, disable_notification=True, type='message')

                # Registering a new PV to an existing PV Group
                elif command[:7] == "/addpv ":
                    pv_str = command[7:]
                    answer = add_pv_to_group(pv_str)
                    send(chat_id, answer, type='message')

                # Requesting administrators to alter a PV group's timeout
                elif command[:12] == "/settimeout" and str(chat_id) not in teams['ADM']:
                    forward_message = "[{}] wishes to alter a PV Group Timeout:\n{}".format(user,command)
                    answer = "Request forwarded to the Bot's administrators"
                    send(chat_id, answer, type='message')
                    log("Set Timeout request", command, user, timestamp=timestamp)
                    # Forwards the message to every administrator
                    for adm in teams['ADM']:
                        send(adm, forward_message, disable_notification=True, type='message')

                # Alters a PV group timeout
                elif command[:12] == "/settimeout ":
                    timeout_string = command[12:]
                    answer = set_timeout(timeout_string)
                    send(chat_id, answer, type='message')
                # Forwarding messages as user
                elif command[:9] == "/forward " and str(chat_id) not in teams['ADM']:
                    forward_message = command[9:]
                    if forward_message:
                        forward_message = "Message forwarded by [" + user + "]:\n" + forward_message
                        for adm in teams['ADM']:
                            send(adm, forward_message, type='message')
                        answer = "Message forwarded to BOT administrators successfully"
                        send(chat_id, answer, type='message')
                    else:
                        error = "Please specify a message to be forwarded"
                        send(chat_id, error, type='message')

                # Forwarding messages as BOT administrator
                elif command[:9] == "/forward ":
                    fwd = command[9:].split(" ")
                    try:
                        # Formats the message to be forwarded and extracts the forward_id
                        forward_id = fwd.pop(0)
                        forward_message = " ".join(fwd)
                        forward_message = "Message forwarded by " + username + ":\n" + forward_message

                        # Verifies if the ID is an authorized user or group
                        if forward_id in authorized_personnel:
                            send(forward_id, forward_message, type='message')
                            answer = "Message forwarded to [{}]:\n{}".format(authorized_personnel[forward_id] + ":" + forward_id, forward_message)
                            send(chat_id, answer, type='message')
                        # Case it's not authorized personnel
                        else:
                            answer = "The specified ChatID is not authorized to use the BOT"
                            send(chat_id, answer, type='message')
                            log("Inconsistency", "[tried to forward a message to an unauthorized ChatID: " + forward_id + "]", user, timestamp = timestamp)
                    # Case the message was formatted wrong
                    except ValueError:
                        answer = """
An error occured while formatting the forward string, maybe you mistyped.
Try again using the format: /forward (chatID) (message)"""
                        send(chat_id, answer, type='message')
                        log("Value Error", "{while forwarding a message. Probably string was formatted wrong: " + command + "}", user)

                # Sends PV_values dictionary
                # elif command == "/pvvalues" and str(chat_id) in teams['ADM']:
                    # val_str = str(PV_values)
                    # send(chat_id, val_str, type='message')

                # Updates all dictionaries and files
                elif command == "/update" and str(chat_id) in teams['ADM']:
                    update_PV_groups()
                    update_personnel()
                    update_PV_values()
                    update_PV_mon()
                    answer = "PVGroups and authorized personnel updated"
                    send(chat_id, answer, type='message')

                # Verifies if monitoring is alive
                elif command == "/isalive":
                    answer = str(t.is_alive())
                    send(chat_id, answer, type='message')

                # Print out PV status
                elif command[:11] == "/getstatus ":
                    pvs = command[11:].split(" ")

                    for pv in pvs:
                        pv_statuses = requests.get("{}/getPVStatus?pv={}&reporttype=short".format(config["mgmtURL"], pv), verify=False).json()

                        for status in pv_statuses:
                            status_msg = "Status for {}: {}".format(status["pvName"], status["status"])

                            if status["status"] == "Being archived":
                                status_msg += "\nConnected: {}\nAppliance: {}\nLast Event: {}\n".format(status["connectionState"], status["appliance"], status["lastEvent"])

                            send(chat_id, status_msg, type='message')

                # Unknown command message
                else:
                    log("Unknown Command", command, user, timestamp=timestamp)
                    answer = "Unknown command, send /help to see the BOT valid commands"
                    send(chat_id, answer, type='message')

            # Case the command is invalid
            else:
                send(chat_id, "Invalid command\nThe Bot cannot process images, GIFs, audios and files", type='message')
                log("New Message", "[invalid command]", user, timestamp=timestamp)
        # Case the chat_id is not authorized registers log message
        else:
            send(chat_id, "Access denied\n" + user, type='message')
            if "text" in msg:
                log("Access Denied", msg['text'], user, timestamp=timestamp)
            else:
                log("Access Denied", "[invalid command]", user, timestamp=timestamp)
    # except Exception as exception:
    #     log(type(exception), exception)

def login(username, password):
    session = requests.Session()
    response = session.post("{}/login".format(config["mgmtURL"]), data = { "username" : username, "password" : password }, verify = False)

    if ("authenticated" in response.text):
        return(session)
    return(None)

def convert_time(seconds):
    if seconds < 3600:
        return "less than an hour"

    days = seconds // 86400
    hours = seconds % 86400 // 3600
    time_string = ""

    if days > 0:
        time_string = "{} {}".format(days, "days" if days > 1 else "day")
    if hours > 0:
        time_string += " " if days > 0 else ""
        time_string += "{} {}".format(hours, "hours" if hours > 1 else "hour")

    return time_string

#Monitors for disconnected PVs and pauses them if they've been disconnected long enough
def monitor_disconnected():
    warn_times = config["warnTimes"] #Times in seconds for 1 week, 2 days and 10 days.

    while(True):
        #Used to guarantee PVs are truly disconnected, as the bot failing to perform a CAGET request could mean other issues.
        disconnected_PVs = requests.get("{}/getCurrentlyDisconnectedPVs".format(config["mgmtURL"]), verify=False).json()
        session = login(api_user, api_pass)

        mutex_csv.acquire()
        monitor_info_df = pandas.read_csv("monitor_info.csv", keep_default_na=False)
        current_time = datetime.datetime.now()-datetime.timedelta(hours=3)

        data_changed = False

        for discPV in disconnected_PVs:
            index = monitor_info_df[monitor_info_df['PVNames']==discPV['pvName']].index.values

            if(len(index) == 1):
                last_event = datetime.datetime.fromtimestamp(float(discPV['noConnectionAsOfEpochSecs']))-datetime.timedelta(hours=3)

                if monitor_info_df.at[index[0], 'DisconnectDate'] == "":
                    last_fetch = last_event
                else:
                    last_fetch = datetime.datetime.strptime(monitor_info_df.at[index[0], 'DisconnectDate'], "%Y-%m-%d %H:%M:%S")

                if(last_event.timestamp() > last_fetch.timestamp()):
                    monitor_info_df.at[index[0], 'DisconnectDate'] = ""
                    monitor_info_df.at[index[0], 'WarningCount'] = 0

                    data_changed = True
                    continue

                warning_count = int(monitor_info_df.at[index[0], 'WarningCount'])
                next_warn = warn_times[warning_count]

                time_dif = current_time.timestamp() - last_fetch.timestamp()


                if (time_dif > next_warn):
                    ChatIDs = monitor_info_df.at[index[0], 'ChatIDs'].split(';')
                    rem_time = warn_times[2] if warning_count == 1 else warn_times[1] + warn_times[2]

                    if warning_count > 1:
                        session.get("{}/pauseArchivingPV?pv={}".format(config["mgmtURL"], discPV['pvName']))
                        warning_msg = 'PV *{}* has been archived, as it has been inactive for a period longer than {}.'.format(discPV['pvName'], convert_time(rem_time + warn_times[0]))

                        monitor_info_df.at[index[0], 'DisconnectDate'] = ""
                        monitor_info_df.at[index[0], 'WarningCount'] = 0

                        data_changed = True
                    else:
                        last_con_date = last_event.strftime("%Y-%m-%d %H:%M:%S") if discPV['lastKnownEvent'] != "Never" else "Never Connected"

                        warning_msg = '''PV *{}* is disconnected since *{}*.
There are *{}* remaining until the PV is considered inactive and archived.'''.format(discPV['pvName'], last_con_date, convert_time(rem_time))
                        print(convert_time(rem_time))
                        print(rem_time)
                        monitor_info_df.at[index[0], 'WarningCount'] = warning_count + 1
                        monitor_info_df.at[index[0], 'DisconnectDate'] = current_time.strftime("%Y-%m-%d %H:%M:%S")

                        data_changed = True
                    for ChatID in ChatIDs:
                        if ChatID in teams:
                            for ind_id in teams[ChatID]:
                                print("Sent message to {}".format(ind_id))
                                send(ind_id, warning_msg, type='message', parse_mode='markdown')
                        else:
                            send(ChatID[ChatID.index(':')+1:], warning_msg, type='message', parse_mode='markdown')
                            print("Sent message to {}".format(ChatID[ChatID.index(':')+1:]))

                    print("Warn {} sent. Last fetch date: {}. Warn time: {}".format(warning_count, last_fetch, next_warn))
        if(data_changed):
            monitor_info_df.to_csv('monitor_info.csv', index=False)
        mutex_csv.release()
        time.sleep(60)

log(message="Initiating BOT")
log(message="Updating dictionaries")
# Updating dictionaries
update_personnel()
update_PV_groups()
update_PV_values()
update_PV_mon()

log(message="Initiating monitor thread")
t = Thread(target=monitor, daemon=True)
t_disc = Thread(target=monitor_disconnected, daemon=True)

log(message="Initiating command handler")
# Initiates action function as a Thread
MessageLoop(telegram_bot, action).run_as_thread()
print("\n\n\n\n\n", telegram_bot.getMe(), "Operating....\n\n")

try:
    t.start()
    t_disc.start()
    while True:
        time.sleep(10)
        if not t.is_alive():
            telegram_bot.sendMessage(31980138, "Thread is dead")
            telegram_bot.sendMessage(653288463, "Thread is dead")
            log("thread died")
            break
    while True:
        time.sleep(10)
except Exception as e:
    log(e, "Good night")
except KeyboardInterrupt:
    log("terminate")

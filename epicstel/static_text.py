import json
from string import Template

command_dict = {}


def gen_strings() -> None:
    with open("data/config.json") as json_config:
        config = json.load(json_config)

    global user_commands
    global team_adm_commands
    global bot_adm_commands

    bot_adm_commands = "\n*Bot Administrator commands:*\n"
    team_adm_commands = "\n*Team Administrator commands:*\n"
    user_commands = "\n*User commands:*\n"

    for k, v in config["user_commands"].items():
        if "syntax" not in v:
            user_commands += "/{} - {}\n".format(k, v["desc"])
        else:
            user_commands += "/{} {} - {}\n".format(k, v["syntax"], v["desc"])

    for k, v in config["teamadm_commands"].items():
        if "syntax" not in v:
            team_adm_commands += "/{} - {}\n".format(k, v["desc"])
        else:
            team_adm_commands += "/{} {} - {}\n".format(k, v["syntax"], v["desc"])

    for k, v in config["adm_commands"].items():
        if "syntax" not in v:
            bot_adm_commands += "/{} - {}\n".format(k, v["desc"])
        else:
            bot_adm_commands += "/{} {} - {}\n".format(k, v["syntax"], v["desc"])

    global command_dict
    command_dict = dict(config["user_commands"])
    command_dict.update(config["teamadm_commands"])
    command_dict.update(config["adm_commands"])


forward_mistype = """
An error occured while formatting the forward string, maybe you mistyped.
Try again using the format: /forward (chatID) (message)"""

links = """For more information check the [Sharepoint page](https://cnpemcamp.sharepoint.com/sites/iot/SitePages/EPICSTel.aspx)
To report bugs or errors, send a message to @patriciahn or @g\_freitas !"""

greeting = Template(
    """Hello there, $NAME! 😊
*Welcome to EPICSTel, an EPICS PV info Bot from CNPEM/IOT group!*
Here are my valid commands:"""
)

monitor_warning = Template(
    """⚠️ *WARNING* 
A Process Variable has exceeded it's $min_or_max limits:
```
Group:   $group
PV:      $pv
Value:   $val
Limit:   $limit```"""
)

check_me = Template(
    """👤 Your user information:```
Username:  $user
Chat ID:   $id
Teams:     $teams
PV groups: $pvgroups
PVs:       $pvs ```"""
)

check_team = Template(
    """ℹ️ *$team*:
Admins:  \n```\n$admins```
Members: \n```\n$members```
PV groups: \n```\n$pvgroups```
PVs: \n```\n$pvs```"""
)

new_pv = Template(
    """ℹ️ *New Process Variable added:*```
PVGroup:  $group
PVName:   $pv
Max:      $max
Min:      $min```"""
)

pv_altered = Template(
    """ℹ️ *PV Limits altered*:
```
PVGroup:  $group
PVName:   $pv
Max:      $max
Min:      $min```"""
)

get_status = Template(
    """
```
Connected:  $connected
Appliance:  $appliance
Last Event: $last_event```"""
)

disconnect_warning = Template(
    """⚠️ PV *$pv* is disconnected since *$disc_date*.
There are *$days* remaining until the PV is considered inactive and archived."""
)

pv_archived = Template("PV *$pv* has been archived, as it has been inactive for a period longer than $disc_time.")

added_personnel = Template(
    """You've been added to the Bot's authorized personnel
Team: $team"""
)

input_date_long = "%Y/%m/%d-%H:%M:%S"
input_date_short = "%Y/%m/%d"

output_date = "%Y-%m-%dT%H:%M:%S.000Z"

import json
import os
import time
import redis

import requests
from bson import ObjectId

from epicstel.bot import TelBot
from epicstel.static_text import disconnect_warning, monitor_warning, pv_archived, bbb_disconnected

SERVER_LIST = [
    "10.0.38.59",
    "10.0.38.46",
    "10.0.38.42",
    "10.128.153.81",
    "10.128.153.82",
    "10.128.153.83",
    "10.128.153.84",
    "10.128.153.85",
    "10.128.153.86",
    "10.128.153.87",
    "10.128.153.88",
]


class Monitor:
    def __init__(self, bot: TelBot, user: str, password: str):
        self.logger = bot.logger
        self.bot = bot

        with open("data/config.json") as json_config:
            config = json.load(json_config)

        self.user = user
        self.password = password
        self.url = "https://10.0.38.42/mgmt/bpl"
        self.times = config["warn_times"]
        self.last_ca_update = 0

        self.find_active()

    def find_active(self):
        while True:
            for server in SERVER_LIST:
                try:
                    remote_db = redis.StrictRedis(host=server, port=6379, socket_timeout=4)
                    remote_db.ping()
                    self.logger.info("Connected to {} Redis Server".format(server))
                    self.redis_db = remote_db
                    return
                except redis.exceptions.ConnectionError:
                    self.logger.warning("{} Redis server is disconnected".format(server))
                except redis.exceptions.ResponseError:
                    self.logger.warning("Could not connect to {}, a response error has ocurred".format(server))
                    time.sleep(30)
                except Exception as e:
                    self.logger.warning("Could not connect to {}: {}".format(server, e))
                    time.sleep(50)
                continue

            self.logger.info("Server not found. Retrying to connect in 10 seconds...")
            time.sleep(10)

    def main(self) -> None:
        while True:
            update_ids = set()
            self.bot.update_pv_values()
            now = time.time()

            if now - self.last_ca_update > 120:
                ip_list = " ".join(self.bot.configs.find_one({"config": "EPICS_CA_ADDR_LIST"}).get("ips"))

                if os.environ["EPICS_CA_ADDR_LIST"] != ip_list:
                    self.logger.info("Updated CA ADDR list: {}".format(os.environ["EPICS_CA_ADDR_LIST"]))
                    self.last_ca_update = now
                    os.environ["EPICS_CA_ADDR_LIST"] = ip_list

            for user in self.bot.users.find(
                {"$or": [{"pvs": {"$elemMatch": {"$exists": True}}}, {"groups": {"$elemMatch": {"$exists": True}}}]}
            ):
                warning_message = ""
                pvs = [pv for pv in self.bot.pvs.find({"group": {"$in": user.get("groups")}, "value": {"$ne": None}})]

                for team in self.bot.teams.find({"team": {"$in": user.get("teams")}}):
                    pvs += [
                        pv for pv in self.bot.pvs.find({"group": {"$in": team.get("groups")}, "value": {"$ne": None}})
                    ]
                    # pvs += self.bot.pvs.find("_id":{"$in":[pv["ext_id"] for pv in team.get("pvs")]})

                pvs += self.bot.pvs.find(
                    {"_id": {"$in": [pv["ext_id"] for pv in user.get("pvs")]}, "value": {"$ne": None}}
                )

                pvs = [
                    dict(t) for t in {tuple(d.items()) for d in pvs if d["_id"] not in user.get("ignore")}
                ]  # Remove duplicates and ignored PVs

                for pv in pvs:
                    if now > pv.get("last_alert") + pv.get("timeout") * 60:
                        exc = None
                        if pv.get("value") > pv.get("max"):
                            exc = "maximum"
                            limit = pv.get("max")
                        elif pv.get("value") < pv.get("min"):
                            exc = "minimum"
                            limit = pv.get("min")

                        if exc:
                            update_ids.add(ObjectId(pv.get("_id")))
                            self.logger.info("{} exceeded its {} limit for user: {}".format(pv.get("name"), exc, user))

                            warning_message += (
                                monitor_warning.safe_substitute(
                                    min_or_max=exc,
                                    group=pv.get("group"),
                                    pv=pv.get("name"),
                                    val=pv.get("value"),
                                    limit=limit,
                                )
                                + "\n"
                            )

                if warning_message:
                    self.bot.bot.send_message(user.get("chat_id"), warning_message, parse_mode="markdown")

            self.bot.pvs.update_many({"_id": {"$in": list(update_ids)}}, {"$set": {"last_alert": now}})

            time.sleep(0.1)

    def login(self) -> requests.Session():
        session = requests.Session()
        response = session.post(
            "{}/login".format(self.url),
            data={"username": self.user, "password": self.password},
            verify=False,
        )

        if "authenticated" in response.text:
            return session
        return None

    def convert_time(self, seconds: int) -> str:
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

    # Monitors for disconnected PVs (and Beaglebones) and pauses PVs if they've been disconnected long enough
    def disc(self) -> None:
        # Times in seconds for 1 week, 2 days and 10 days.
        warn_times = self.times

        while True:
            try:
                disconnectedBBBs = self.redis_db.smembers("DisconnectedWarn")
                if disconnectedBBBs:
                    for bbb in disconnectedBBBs:
                        for user in self.bot.users.find({"bbbWarn": True}):
                            bbb_info = bbb.decode()[4:].split(":")
                            full_str = "{} ({})".format(bbb_info[0], ":".join(bbb_info[1:]))
                            self.bot.bot.send_message(
                                user.get("chat_id"),
                                bbb_disconnected.safe_substitute(BBB=full_str),
                                parse_mode="markdown",
                            )
                    
                    self.redis_db.delete("DisconnectedWarn")
            except Exception as e:
                print(e)
                self.find_active()

            # Used to guarantee PVs are truly disconnected,
            # as the bot failing to perform a CAGET request could mean other issues.
            disconnected_PVs = requests.get("{}/getCurrentlyDisconnectedPVs".format(self.url), verify=False).json()
            session = self.login()

            current_time = time.time()

            for pv in disconnected_PVs:
                local_pv = self.bot.pvs.find_one({"name": pv["pvName"]})
                if not local_pv:
                    continue

                last_event = float(pv["noConnectionAsOfEpochSecs"])

                if last_event > local_pv.get("d_time") or local_pv.get("d_count") == 4:
                    self.bot.pvs.update_one(local_pv._id, {"d_time": 0, "d_count": 0})
                    continue

                next_warn = warn_times[local_pv.get("d_count")]
                time_dif = current_time - local_pv.get("d_time")

                if time_dif > next_warn:
                    chat_ids = self.bot.users.find({"pvs": {"name": {"$in": pv["pvName"]}}})
                    if len(chat_ids) == 0:
                        continue

                    rem_time = warn_times[2] if local_pv.get("d_count") == 1 else warn_times[1] + warn_times[2]

                    if local_pv.get("d_count") > 1:
                        session.get("{}/pauseArchivingPV?pv={}".format(self.url, pv["pvName"]))
                        warning_msg = pv_archived.safe_substitute(
                            pv=pv["pvName"], disc_time=self.convert_time(rem_time + warn_times[0])
                        )

                        self.bot.pvs.update_one(local_pv._id, {"d_time": 0, "d_count": 0})
                    else:
                        warning_msg = disconnect_warning.safe_substitute(
                            pv=pv["pvName"], disc_date=pv["lastKnownEvent"], days=self.convert_time(rem_time)
                        )

                        self.bot.pvs.update_one(local_pv._id, {"d_time": current_time, "$inc": {"d_count": 1}})
                    for c in chat_ids:
                        self.bot.bot.send_message(c.get("chat_id"), warning_msg, parse_mode="markdown")

            time.sleep(60)

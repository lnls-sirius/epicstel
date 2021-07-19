# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.1] - 2021-07-06
### Changed
- /unsubscribepv and /subscribepv functions are now able to affect group subscribes dynamically 

## [4.0.0] - 2021-06-17
### Added
- Get team info (/getteams) command, substitutes /getids
- Remove team command (/removeteam), accessible only by admins
- Subscribe to single PV functionality (/subscribepv and /unsubscribepv)

### Changed
- Reduces Docker image size further (from ~900MB to ~800MB)
- Uses MongoDB instead of CSV files now
- Team admins are now only able to edit team data pertaining to their teams
- PVs can have individual timeouts
- /checkme command shows subscribed groups and PVs
- Team modification requests are forwarded to admins
- User ID is completely separate from the user's name, which is only used when displaying user info
- /getstatus (now /checkstatus) was renamed to match the naming pattern for all commands 

### Removed
- Private chat subscribe limitation (bot can send messages in group)
- /getids command (substituted by the /checkteam command, with more features)
- /pause, /unpause (PVs can be individually subscribed/unsubscribed to now)
- /pvgroupsfile, /update (CSV files are no longer being used)
- /fullreset
- TeamADMs group (superseded by granular admin functionality)
- A ton of non-atomic test cases
- Pandas, Cython dependencies


## [3.0.0] - 2021-05-25 (Yanked)
### Added
- Full reset (/fullreset) function to reload all files during testing
- Error handler to prevent leaving users "in the dark", sends stack trace (and other telemetry) to developer
- Uses "is typing" status to indicate to users that something is being done
- Integration tests for every command
- Changelog
- Automatically generates command handlers, descriptions and syntax based on config file 
- EPICSTel UI is now available on PyDM-OPI
- User can now plots PVs on Telegram (/plot)
- Extra warnings for certain situations to decrease user confusion
- User can now view latest changelog (/changelog)

### Changed
- Overhauls Docker image to be based on Python 3.7, Debian 10 (slim) and EPICS 3.18, with major improvements in size (from 1.6GB to 963MB)
- Swaps out unmaintained Telepot module for Python-Telegram-Bot, with more features, handlers and performance improvements
- Improvements to message formatting, using markdown
- Fixes folder nomenclature
- Uses templates for static text more consistenly
- Uses caget to check PV status instead of initializing and denitializing PV object (saves memory and CPU usage)

### Fixes
- Updates Pandas to 1.2.4 (fixes parallel file access SEGFAULT), PyEpics to 3.4.3 (fixes caget SEGFAULT) for better stability
- Numerous mutex lock fixes
- Unlocks mutexes on error state
- Shuts up warnings from Pandas and Requests lib
- Fixes multiple no-message returns


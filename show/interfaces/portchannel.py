import click
import utilities_common.cli as clicommon
from natsort import natsorted
from tabulate import tabulate
import utilities_common.multi_asic as multi_asic_util
from utilities_common.constants import PORT_CHANNEL_OBJ

"""
    Script to show LAG and LAG member status in a summary view
    Example of the output:
    acsadmin@sonic:~$ teamshow
    Flags: A - active, I - inactive, Up - up, Dw - down, N/A - Not Available,
           S - selected, D - deselected, * - not synced
     No.  Team Dev       Protocol    Ports
    -----  -------------  ----------  ---------------------------
        0  PortChannel0   LACP(A)(Up)     Ethernet0(D) Ethernet4(S)
        8  PortChannel8   LACP(A)(Up)     Ethernet8(S) Ethernet12(S)
       16  PortChannel16  LACP(A)(Up)     Ethernet20(S) Ethernet16(S)
       24  PortChannel24  LACP(A)(Dw)     Ethernet28(S) Ethernet24(S)
       32  PortChannel32  LACP(A)(Up)     Ethernet32(S) Ethernet36(S)
       40  PortChannel40  LACP(A)(Dw)     Ethernet44(S) Ethernet40(S)
       48  PortChannel48  LACP(A)(Up)     Ethernet52(S) Ethernet48(S)
       56  PortChannel56  LACP(A)(Dw)     Ethernet60(S) Ethernet56(S)

"""

PORT_CHANNEL_APPL_TABLE_PREFIX = "LAG_TABLE:"
PORT_CHANNEL_CFG_TABLE_PREFIX = "PORTCHANNEL|"
PORT_CHANNEL_STATE_TABLE_PREFIX = "LAG_TABLE|"
PORT_CHANNEL_STATUS_FIELD = "oper_status"
PORT_CHANNEL_LACP_KEY_FIELD = "lacp_key"
PORT_CHANNEL_FAST_RATE_FIELD = "fast_rate"
PORT_CHANNEL_MIX_SPEED_FIELS = "mix_speed"

PORT_APPL_TABLE_PREFIX = "PORT_TABLE:"

PORT_CHANNEL_MEMBER_APPL_TABLE_PREFIX = "LAG_MEMBER_TABLE:"
PORT_CHANNEL_MEMBER_STATE_TABLE_PREFIX = "LAG_MEMBER_TABLE|"
PORT_CHANNEL_MEMBER_STATUS_FIELD = "status"

class Teamshow(object):
    def __init__(self, namespace_option, display_option):
        self.teams = []
        self.teamsraw = {}
        self.summary = {}
        self.err = None
        self.db = None
        self.multi_asic = multi_asic_util.MultiAsic(display_option, namespace_option)

    @multi_asic_util.run_on_multi_asic
    def get_teams_info(self):
        self.get_portchannel_names()
        self.get_teamdctl()
        self.get_teamshow_result()

    def get_portchannel_names(self):
        """
            Get the portchannel names from database.
        """
        self.teams = []
        team_keys = self.db.keys(self.db.CONFIG_DB, PORT_CHANNEL_CFG_TABLE_PREFIX+"*")
        if team_keys is None:
            return
        for key in team_keys:
            team_name = key[len(PORT_CHANNEL_CFG_TABLE_PREFIX):]
            if self.multi_asic.skip_display(PORT_CHANNEL_OBJ, team_name) is True:
                continue
            self.teams.append(team_name)

    def get_portchannel_status(self, port_channel_name):
        """
            Get port channel status from database.
        """
        full_table_id = PORT_CHANNEL_APPL_TABLE_PREFIX + port_channel_name
        return self.db.get(self.db.APPL_DB, full_table_id, PORT_CHANNEL_STATUS_FIELD)

    def get_portchannel_member_status(self, port_channel_name, port_name):
        full_table_id = PORT_CHANNEL_MEMBER_APPL_TABLE_PREFIX + port_channel_name + ":" + port_name
        return self.db.get(self.db.APPL_DB, full_table_id, PORT_CHANNEL_MEMBER_STATUS_FIELD)

    def get_portchannel_admin_key(self, port_channel_name):
        """
            Get port channel admin lacp key from database.
        """
        full_table_id = PORT_CHANNEL_CFG_TABLE_PREFIX + port_channel_name
        return self.db.get(self.db.CONFIG_DB, full_table_id, PORT_CHANNEL_LACP_KEY_FIELD)

    def get_portchannel_fast_rate(self, port_channel_name):
        """
            Get port channel fast rate from database.
        """
        full_table_id = PORT_CHANNEL_CFG_TABLE_PREFIX + port_channel_name
        return self.db.get(self.db.CONFIG_DB, full_table_id, PORT_CHANNEL_FAST_RATE_FIELD)

    def get_portchannel_oper_key(self, port_name):
        """
            Get port channel oper lacp key from database.
        """
        full_table_id = PORT_APPL_TABLE_PREFIX + port_name
        return self.db.get(self.db.APPL_DB, full_table_id, PORT_CHANNEL_LACP_KEY_FIELD)

    def get_portchannel_mix_speed(self, port_channel_name):
        """
            Get port channel admin lacp key from database.
        """
        full_table_id = PORT_CHANNEL_CFG_TABLE_PREFIX + port_channel_name
        return self.db.get(self.db.CONFIG_DB, full_table_id, PORT_CHANNEL_MIX_SPEED_FIELS)

    def get_team_id(self, team):
        """
            Skip the 'PortChannel' prefix and extract the team id.
        """
        return team[11:]

    def get_teamdctl(self):
        """
            Get teams raw data from teamdctl.
            Command: 'teamdctl <teamdevname> state dump'.
        """

        team_keys = self.db.keys(self.db.STATE_DB, PORT_CHANNEL_STATE_TABLE_PREFIX+"*")
        if team_keys is None:
            return
        _teams = [key[len(PORT_CHANNEL_STATE_TABLE_PREFIX):] for key in team_keys]

        for team in self.teams:
            if team in _teams:
                self.teamsraw[self.get_team_id(team)] = self.db.get_all(self.db.STATE_DB, PORT_CHANNEL_STATE_TABLE_PREFIX+team)

    def get_teamshow_result(self):
        """
             Get teamshow results by parsing the output of teamdctl and combining port channel status.
        """
        for team in self.teams:
            info = {}
            team_id = self.get_team_id(team)
            if team_id not in self.teamsraw:
                info['protocol'] = 'N/A'
                self.summary[team_id] = info
                self.summary[team_id]['ports'] = ''
                self.summary[team_id]['admin_key'] = ''
                self.summary[team_id]['oper_key'] = ''
                self.summary[team_id]['fast_rate'] = ''
                self.summary[team_id]['mix_speed'] = False
                continue
            state = self.teamsraw[team_id]
            if state['setup.runner_name'] == 'lacp':
                info['protocol'] = "LACP"
                info['protocol'] += "(A)" if state['runner.active'] == "true" else '(I)'
                fast_rate = self.get_portchannel_fast_rate(team)
                info['fast_rate'] = fast_rate if fast_rate == "true" else "false"
            else:
                info['protocol'] = "NONE"
                info['protocol'] += "(-)"
                info['fast_rate'] = "N/A"

            portchannel_status = self.get_portchannel_status(team)
            if portchannel_status is None:
                info['protocol'] += '(N/A)'
            elif portchannel_status.lower() == 'up':
                info['protocol'] += '(Up)'
            elif portchannel_status.lower() == 'down':
                info['protocol'] += '(Dw)'
            else:
                info['protocol'] += '(N/A)'

            info['ports'] = ""
            info['oper_key'] = 'N/A'

            admin_key = self.get_portchannel_admin_key(team)
            info['admin_key'] = admin_key if admin_key else 'N/A'

            mix_speed = self.get_portchannel_mix_speed(team) == "true"
            info['mix_speed'] = mix_speed

            member_keys = self.db.keys(self.db.STATE_DB, PORT_CHANNEL_MEMBER_STATE_TABLE_PREFIX+team+'|*')
            if not member_keys:
                info['ports'] = 'N/A'
            else:
                ports = [key[len(PORT_CHANNEL_MEMBER_STATE_TABLE_PREFIX+team+'|'):] for key in member_keys]
                break_line = False
                for port in ports:
                    status = self.get_portchannel_member_status(team, port)
                    pstate = self.db.get_all(self.db.STATE_DB, PORT_CHANNEL_MEMBER_STATE_TABLE_PREFIX+team+'|'+port)
                    if state['setup.runner_name'] == 'lacp':
                        selected = True if pstate['runner.aggregator.selected'] == "true" else False
                    else:
                        selected = True if pstate['link_watches.list.link_watch_0.up'] == "true" else False
                    if clicommon.get_interface_naming_mode() == "alias":
                        alias = clicommon.InterfaceAliasConverter().name_to_alias(port)
                        info["ports"] += alias + "("
                    else:
                        info["ports"] += port + "("
                    info["ports"] += "S" if selected else "D"
                    if status is None or (status == "enabled" and not selected) or (status == "disabled" and selected):
                        info["ports"] += "*"
                    info["ports"] += ") "
                    if break_line:
                        info["ports"] += "\n"
                    break_line ^= 1
                oper_key = self.get_portchannel_oper_key(next(iter(ports)))
                if oper_key:
                    info['oper_key'] = oper_key

            self.summary[team_id] = info

    def display_summary(self):
        """
            Display the portchannel (team) summary.
        """
        print("Flags: A - active, I - inactive, Up - up, Dw - Down, N/A - not available,\n"
              "       S - selected, D - deselected, * - not synced,\n"
              "       M - mixed speed")

        header = ['No.', 'Team Dev', 'Protocol', 'Ports', 'Oper Key', 'Admin Key', 'Fast Rate']
        output = []
        for team_id in natsorted(self.summary):
            output.append([team_id, 'PortChannel'+team_id+("(M)"if self.summary[team_id]['mix_speed'] else ""), \
            self.summary[team_id]['protocol'], self.summary[team_id]['ports'], \
            self.summary[team_id]['oper_key'], self.summary[team_id]['admin_key'], self.summary[team_id]['fast_rate']])
        print(tabulate(output, header))

# 'portchannel' subcommand ("show interfaces portchannel")
@click.command()
@multi_asic_util.multi_asic_click_options
@click.option('--verbose', is_flag=True, help="Enable verbose output")
def portchannel(namespace, display, verbose):
    """Show PortChannel information"""
    team = Teamshow(namespace, display)
    team.get_teams_info()
    team.display_summary()

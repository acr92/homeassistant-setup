import minimalmodbus
import datetime

REGISTER_INDEX = 0
FUNCTIONCODE_INDEX = 1
NAME_INDEX = 2
DECIMALS_INDEX = 3
TARGET_VALUE_INDEX = 4
CURRENT_VALUE_INDEX = 4
LAST_READING_INDEX = 5

DEFAULT_UNIT_STATUS = [[5001, 3, "Operating Mode", 0, 2, 2]]

DEFAULT_SENSORS = [[6201, 4, "Fresh Air Temperature", 1, -550, -550],
                   [6202, 4, "Supply air before re-heater temperature", 1, -550, -550],
                   [6203, 4, "Supply air temperature", 1, -550, -550],
                   [6204, 4, "Extract air temperature", 1, -550, -550],
                   [6205, 4, "Exhaust (waste) air temperature", 1, -550, -550],
                   [6206, 4, "Room air temperature", 1, -550, -550],
                   [6207, 4, "User Panel 1 temperature", 1, -550, -550],
                   [6208, 4, "User Panel 2 temperature", 1, -550, -550],
                   [6209, 4, "Water Radiator temperature", 1, -550, -550],
                   [6210, 4, "Pre-heater temperature", 1, -550, -550],
                   [6211, 4, "External Fresh air temperature", 1, -550, -550],
                   [6212, 4, "CO2 Unfiltered", 0, 0, 0],
                   [6213, 4, "CO2 Filtered", 0, 0, 0],
                   [6214, 4, "RH", 0, 0, 0]]

DEFAULT_ALARMS = [[6132, 4, "Active Alarms", 0, 0, 0]]

DEFAULT_SETTINGS = [[5101, 3, "Temperature setpoint", 0, 23, 0]]

# Misc registers
FAN_MODE_REGISTER = 5001
FAN_MODES = ["Stopped", "Away", "Home", "Boost", "Travelling"]
TEMPERATURE_SETPOINT_REGISTER = 5101

# --------------------------------------------------
# Public API
# --------------------------------------------------


class Swegon(object):
    def __init__(self, debug_function):
        self.status = DEFAULT_UNIT_STATUS
        self.sensors = DEFAULT_SENSORS
        self.alarms = DEFAULT_ALARMS
        self.settings = DEFAULT_SETTINGS
        self.startup_time = datetime.datetime.now()
        self.debug = debug_function
        self.modbus = minimalmodbus.Instrument('/dev/ttyS0', 1)
        self.modbus.serial.baudrate = 38400
        self.get_swegon_data()

    # Mode assumed to be {Away, Home, Boost, Compensate}
    def set_fan_mode(self, mode):
        value = FAN_MODES.index(mode)
        self._write_register(FAN_MODE_REGISTER, value, 0)

    # Temperature assumed to have one decimal, i.e. 20.0
    def set_temperature(self, temperature):
        target = round(float(temperature))
        self._write_register(TEMPERATURE_SETPOINT_REGISTER, target, 0)

    def reset_alarms(self):
        self.debug("Clearing all alarms")
        # TODO

    # Returns 4 dicts with different data sets {settings, status, sensors, alarms}
    def get_swegon_data(self):
        success = False
        while not success:
            success = True
            self._read(self.status)
            self._read(self.sensors)
            self._read(self.alarms)
            self._read(self.settings)

            if not success:
                self.debug("Re-running data reading")

        return self._process_data()

    # --------------------------------------------------
    # Internal functions: read and write
    # --------------------------------------------------

    def _write_register(self, register, value, decimals=0):
        self.modbus.write_register(register - 1, value, number_of_decimals=decimals, functioncode=6, signed=True)
        return True

    def _read_register(self, register, functioncode, decimals=0):
        return self.modbus.read_register(register - 1, decimals, functioncode=functioncode, signed=True)

    def _read_registers(self, base, functioncode, length):
        return self.modbus.read_registers(base - 1, length, functioncode)

    # --------------------------------------------------
    # Internal functions: post-processing
    # --------------------------------------------------

    # Post-processes, returns all dicts
    def _process_data(self):
        settings_data = self._process_settings()
        status_data = self._process_status()
        sensors_data = self._process_sensors()
        alarms_data = self._process_alarms()
        return [settings_data, status_data, sensors_data, alarms_data]

    def _process_settings(self):
        self._register_new_measurements(self.settings)
        data = self._convert_raw_table(self.settings)
        return data

    def _process_status(self):
        self._register_new_measurements(self.status)
        data = self._convert_raw_table(self.status)
        data["Mode"] = FAN_MODES[data["Operating Mode"]]
        data["Controller uptime"] = self._get_controller_uptime()
        return data

    def _process_alarms(self):
        self._register_new_measurements(self.alarms)
        data = self._convert_raw_table(self.alarms)
        data["Alarms"] = self._get_alarms_string()
        return data

    def _process_sensors(self):
        self._register_new_measurements(self.sensors)
        data = {}
        for sensor in self.sensors:
            data[sensor[NAME_INDEX]] = sensor[CURRENT_VALUE_INDEX]
        return data

    def _register_new_measurements(self, table):
        for item in table:
            item[CURRENT_VALUE_INDEX] = item[LAST_READING_INDEX]

    def _convert_raw_table(self, table):
        data = {}
        for item in table:
            data[item[NAME_INDEX]] = item[CURRENT_VALUE_INDEX]
        return data

    def _get_alarms_string(self):
        alarms = "None"
        for alarm in self.alarms:
            if alarm[CURRENT_VALUE_INDEX]:
                if alarms == "None":
                    alarms = alarms[NAME_INDEX]
                else:
                    alarms += ", " + alarms[NAME_INDEX]
        return alarms

    def _get_controller_uptime(self):
        uptime_delta = datetime.datetime.now() - self.startup_time
        uptime_string = ':'.join(str(uptime_delta).split(':')[:2])
        return uptime_string

    # --------------------------------------------------
    # Internal functions: Misc
    # --------------------------------------------------

    def _get_value(self, register, table):
        for entry in table:
            if entry[REGISTER_INDEX] == register:
                return entry[CURRENT_VALUE_INDEX]

    def _get_last_reading(self, register, table):
        for entry in table:
            if entry[REGISTER_INDEX] == register:
                return entry[LAST_READING_INDEX]

    def _read(self, table):
        base = table[0][REGISTER_INDEX]
        end_register = table[len(table) - 1][REGISTER_INDEX]
        function_code = table[0][1]
        length = end_register - base + 1

        if length > len(table):
            for entry in table:
                entry[LAST_READING_INDEX] = self._read_register(entry[REGISTER_INDEX], entry[FUNCTIONCODE_INDEX], entry[DECIMALS_INDEX])
            return

        data = self._read_registers(base, function_code, length)

        for offset, value in enumerate(data):
            register = base + offset
            value = self._unsigned_to_signed(value)
            for entry in table:
                if entry[REGISTER_INDEX] == register:
                    if entry[DECIMALS_INDEX]:
                        value = round(value / 10 ** entry[DECIMALS_INDEX], entry[DECIMALS_INDEX])
                    if entry[LAST_READING_INDEX] != value:
                        entry[LAST_READING_INDEX] = value
                        self.debug("Read " + entry[NAME_INDEX] + ": " + str(value))

    def _unsigned_to_signed(self, value):
        ret = value
        if value > 32768:
            ret = value - 65536
        return ret

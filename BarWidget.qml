import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "msi.gp66-fan-control"

  property string mode: "unavailable"
  property string cpuTemp: "—"
  property string gpuTemp: "—"
  property bool coolerBoost: false
  property string backendError: ""
  property var modes: []
  property int modeIndex: 0
  property string helperPath: "/usr/local/libexec/msi-gp66-fan-helper"
  property string clientPath: "/usr/local/libexec/msi-gp66-fan-client"

  function refresh() {
    if (!probe.running) probe.running = true
  }

  function cycleMode(delta) {
    return
  }

  function setCoolerBoost(enabled) {
    if (boostProcess.running) return
    boostProcess.command = ["python3", root.clientPath, "cooler-boost",
      enabled ? "on" : "off"]
    boostProcess.running = true
  }

  implicitWidth: Style.bar.statusSlot
  implicitHeight: button.implicitHeight

  Process {
    id: probe
    command: ["python3", root.clientPath, "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var values = JSON.parse(text)
          root.backendError = values.ok ? "" : (values.error || "fan service unavailable")
          root.mode = values.ok ? (values.mode || "unknown") : "unavailable"
          root.cpuTemp = values.ok ? String(values.cpu_temp) : "—"
          root.gpuTemp = values.ok ? String(values.gpu_temp) : "—"
          root.coolerBoost = values.ok && values.cooler_boost
          root.modes = values.ok ? (values.available_modes || []) : []
          root.modeIndex = Math.max(0, root.modes.indexOf(root.mode))
        } catch (error) {
          root.mode = "unavailable"
          root.cpuTemp = "—"
          root.gpuTemp = "—"
          root.coolerBoost = false
          root.modes = []
          root.backendError = "fan service unavailable"
        }
      }
    }
  }

  Process {
    id: boostProcess
    onExited: root.refresh()
  }

  Timer { interval: 10000; running: true; repeat: true; onTriggered: root.refresh() }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰈐"
    slotSize: Style.bar.statusSlot
    tooltipText: root.modes.length
      ? ("CPU " + root.cpuTemp + "°C · GPU " + root.gpuTemp + "°C\n" +
         "Mode: " + root.mode + " · Cooler Boost: " + (root.coolerBoost ? "on" : "off") +
         "\nLeft-click: enable · Right-click: disable · Middle-click: refresh")
      : ("MSI GP66 fan service unavailable\n" + root.backendError +
         "\nStart msi-gp66-fan-control.service")
    onPressed: function(b) {
      if (b === Qt.MiddleButton) root.refresh()
      else if (b === Qt.LeftButton) root.setCoolerBoost(true)
      else if (b === Qt.RightButton) root.setCoolerBoost(false)
    }
  }

  Component.onCompleted: root.refresh()
}

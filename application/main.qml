import QtQuick
import QtQuick.Controls
import QtQuick.Effects

ApplicationWindow {
    id: mainWindow
    visible: true
    visibility: Window.Maximized
    width: 1366
    height: 768
    flags: Qt.FramelessWindowHint, Qt.Window | Qt.WindowStaysOnTopHint

    property QtObject backend
    property string backendStatus: ""
    property string backendStatusText: ""
    property string registrationStatus: ""
    property string registrationStatusText: ""
    property string readerStatus: ""
    property string readerStatusText: ""
    property string printerStatus: ""
    property string printerStatusText: ""
    property string overallStatus: ""
    property string message: ""
    property int iteration: 1
    property string printStationRegistrationName: ""
    property bool batteryCharging: false
    property int batteryPercentage: 100

    FontLoader {
        id: helsinkiGrotesk
        source: "qrc:/assets/HelsinkiGrotesk-Medium.otf"
    }

    Connections {
        target: mainWindow.backend
        function onIteration_sig(it) {
            mainWindow.iteration = it;
        }
        function onBackend_state_sig(msg) {
            mainWindow.backendStatus = msg;
        }
        function onBackend_statustext_sig(msg) {
            mainWindow.backendStatusText = msg;
        }
        function onRegistration_state_sig(msg) {
            mainWindow.registrationStatus = msg;
        }
        function onRegistration_statustext_sig(msg) {
            mainWindow.registrationStatusText = msg;
        }
        function onReader_state_sig(msg) {
            mainWindow.readerStatus = msg;
        }
        function onReader_statustext_sig(msg) {
            mainWindow.readerStatusText = msg;
        }
        function onPrinter_state_sig(msg) {
            mainWindow.printerStatus = msg;
        }
        function onPrinter_statustext_sig(msg) {
            mainWindow.printerStatusText = msg;
        }
        function onOverall_state_sig(msg) {
            mainWindow.overallStatus = msg;
        }
        function onMessage_sig(msg) {
            mainWindow.message = msg;
        }
        function onPrint_station_registration_name_sig(msg) {
            mainWindow.printStationRegistrationName = msg;
        }
        function onBatterycharging_sig(msg) {
            mainWindow.batteryCharging = msg;
        }
        function onBatterypercentage_sig(msg) {
            mainWindow.batteryPercentage = msg;
        }

    }

    component StatusBox: Rectangle {
        id: statusBox
        
        property string text: ""
        property string logosource: ""
        property real logoOpacity: 1
        property color backgroundColor: "white"
        property color foregroundColor: "black"
        
        FontLoader {
            id: helsinkiGrotesk
            source: "qrc:/assets/HelsinkiGrotesk-Medium.otf"
        }

        width: 200
        color: backgroundColor

        Rectangle {

            height: parent.height
            width: childrenRect.width
            anchors.centerIn: parent
            color: statusBox.backgroundColor
            
            Image {
                id: logo
                source: statusBox.logosource
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                visible: false 
            }
            
            MultiEffect {
                source: logo
                anchors.fill: logo
                colorization: 1.0
                colorizationColor: statusBox.foregroundColor
                opacity: logoOpacity
            }
            
            Text {
                id: textbox
                anchors.left: logo.right
                anchors.leftMargin: 20
                anchors.bottom: logo.bottom
                text: statusBox.text
                font.pixelSize: 16
                font.family: helsinkiGrotesk.name
                font.weight: 400
                color: statusBox.foregroundColor
            }
        }
    }


    Rectangle {
        anchors.fill: parent
        color: "white"
    }

    Rectangle {
        id: topbar
        height: 128
        width: parent.width
        Rectangle {
            id: topbarfill
            anchors.top: parent.top
            height: 43
            width: parent.width
            color: "#9fc9eb"
        }
        Image {
            id: koros
            source: "qrc:/assets/koros-beat.svg"
            anchors.top: topbarfill.bottom
            anchors.left: parent.left
            height: 85
            width: parent.width
            fillMode: Image.Tile
            mirrorVertically: true
            visible: false 
        }
        MultiEffect {
            source: koros
            anchors.fill: koros
            colorization: 1.0
            colorizationColor: "#9fc9eb"
        }
        Image {
            id: helsinkilogo
            source: "qrc:/assets/helsinki-fi-m-black.svg"
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: (parent.height - implicitHeight) / 2
            visible: true 
        }
        Text {
            id: titleText
            font.family: helsinkiGrotesk.name
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: helsinkilogo.right
            anchors.leftMargin: 20
            text: "Signum-savotta"
            font.pixelSize: 32
            color: "black"
        }
        Text {
            id: printStationName
            font.family: helsinkiGrotesk.name
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: batteryStatus.left
            anchors.rightMargin: 20
            text: "Tulostusasema " + mainWindow.printStationRegistrationName
            font.pixelSize: 32
            color: "white"
        }
        Rectangle {
            id: batteryStatus
            anchors.right: parent.right
            anchors.rightMargin: (parent.height - helsinkilogo.implicitHeight) / 2
            anchors.verticalCenter: parent.verticalCenter
            width: 48
            height: childrenRect.height
            color: "transparent"
            Image {
                id: batteryIcon
                source:
                    mainWindow.batteryCharging == true ? "qrc:/assets/ic_fluent_battery_charge_32_regular.svg" :
                    (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 == 10) ? "qrc:/assets/ic_fluent_battery_10_32_regular.svg" :
                    (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 == 9) ? "qrc:/assets/ic_fluent_battery_9_32_regular.svg" :
                    (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 == 8) ? "qrc:/assets/ic_fluent_battery_8_32_regular.svg" :
                    (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 == 7) ? "qrc:/assets/ic_fluent_battery_7_32_regular.svg" :
                    (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 == 6) ? "qrc:/assets/ic_fluent_battery_6_32_regular.svg" :
                    (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 == 5) ? "qrc:/assets/ic_fluent_battery_5_32_regular.svg" :
                    (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 == 4) ? "qrc:/assets/ic_fluent_battery_4_32_regular.svg" :
                    (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 == 3) ? "qrc:/assets/ic_fluent_battery_3_32_regular.svg" :
                    (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 == 2) ? "qrc:/assets/ic_fluent_battery_2_32_regular.svg" :
                    (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 == 1) ? "qrc:/assets/ic_fluent_battery_1_32_regular.svg" :
                    "qrc:/assets/ic_fluent_battery_0_32_regular.svg"
                anchors.top: parent.top
                anchors.horizontalCenter: parent.horizontalCenter
                visible: false 
            }
            MultiEffect {
                source: batteryIcon
                anchors.fill: batteryIcon
                colorization: 1.0
                colorizationColor: (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 > 2 || mainWindow.batteryCharging) ? "#ffffff" : "#b01038"
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: batteryIcon.bottom
                font.family: helsinkiGrotesk.name
                font.pixelSize: 16
                color: (Math.floor(Math.abs(mainWindow.batteryPercentage) / 10) % 10 > 2 || mainWindow.batteryCharging) ? "#ffffff" : "#b01038"
                text: (mainWindow.batteryCharging) ? "Latautuu" : mainWindow.batteryPercentage + "%"
            }

        }

    }

    Rectangle {

        anchors.top: topbar.bottom
        anchors.bottom: statusBar.top
        anchors.left: parent.left
        anchors.leftMargin: Math.max(0, (mainWindow.width - 1366)/2)
        width: mainWindow.width - Math.max(0, (mainWindow.width - 1366)/2)

        Rectangle {

            anchors.centerIn: parent
            width: parent.width
            
            Image {
                id: overallStatusIcon
                source: 
                    (mainWindow.overallStatus == "READY_TO_USE") ? "qrc:/assets/check-circle-fill.svg" : 
                    (mainWindow.overallStatus == "READY_WITH_ERROR") ? "qrc:/assets/alert-circle-fill.svg" :
                    (mainWindow.overallStatus == "BATTERY_LOW") ? "qrc:/assets/ic_fluent_battery_warning_regular.svg" :
                    "qrc:/assets/error-fill.svg"
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                visible: false 
            }
            
            MultiEffect {
                source: overallStatusIcon
                anchors.fill: overallStatusIcon
                colorization: 1.0
                colorizationColor:
                    (mainWindow.overallStatus == "READY_TO_USE") ? "#007a64" :
                    (mainWindow.overallStatus == "READY_WITH_ERROR") ? "#ffda07" :
                    "#b01038"
            }
            
            Text {
                color: "#333333"
                width: parent.width - overallStatusIcon.width - 40 - Math.max(0, (mainWindow.width - 1366)/2)
                wrapMode: Text.WordWrap
                anchors.left: overallStatusIcon.right
                anchors.leftMargin: 20
                anchors.verticalCenter: parent.verticalCenter
                text: mainWindow.message
                textFormat: Text.RichText
                font.pixelSize: 32
                font.family: helsinkiGrotesk.name
            }
        }
    }

    Rectangle {
        id: statusBar
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        width: parent.width
        height: 64

        StatusBox {
            id: backendStatusBox
            
            height: parent.height
            width: parent.width / 4
            anchors.left: parent.left
            anchors.bottom: parent.bottom

            text: backendStatusText
            logosource: "qrc:/assets/company.svg"
            backgroundColor: "#F2F2F2"
            foregroundColor: "#333333"
        }

        StatusBox {
            id: registrationStatusBox
            
            height: parent.height
            width: parent.width / 4
            anchors.left: backendStatusBox.right
            anchors.bottom: parent.bottom

            text: mainWindow.registrationStatusText
            logosource: "qrc:/assets/shield.svg"
            backgroundColor: "#F2F2F2"
            foregroundColor: "#333333"
        }

        StatusBox {
            id: readerStatusBox
            
            height: parent.height
            width: parent.width / 4
            anchors.left: registrationStatusBox.right
            anchors.bottom: parent.bottom

            text: mainWindow.readerStatusText
            logosource: "qrc:/assets/wifi.svg"
            logoOpacity: 0.5 + 0.05 * mainWindow.iteration
            backgroundColor: "#F2F2F2"
            foregroundColor: "#333333"
        }


        StatusBox {
            id: printerStatusBox
            
            height: parent.height
            width: parent.width / 4
            anchors.bottom: parent.bottom
            anchors.right: parent.right

            text: mainWindow.printerStatusText
            logosource: "qrc:/assets/printer.svg"
            backgroundColor: "#F2F2F2"
            foregroundColor: "#333333"
        }

    }

}
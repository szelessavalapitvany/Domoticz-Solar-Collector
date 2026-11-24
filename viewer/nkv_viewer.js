var hardwareReq   = "/json.htm?type=command&param=gethardware";
var tempReq       = "/json.htm?type=command&param=graph&sensor=temp&range=day&idx=";
var tempName      = "/json.htm?type=command&param=getdevices&filter=temp&order=Name";
var switchReq = "/json.htm?type=command&param=getlightlog&idx=";
var switchName    = "/json.htm?type=command&param=getdevices&filter=lightlog&order=Name";
var devicesReq    = "/json.htm?type=command&param=getdevices";
var PercentageReq = "/json.htm?type=command&param=graph&sensor=Percentage&range=day&idx=";
var utilityReq    = "/json.htm?type=command&param=graph&sensor=counter&range=day&idx=";
var setpointReq   = "/json.htm?type=command&param=getdevices&rid=";
var settingsReg   = "/json.htm?type=command&param=getsettings";

var KollektorKontroller = window.KollektorKontroller || class {
	constructor() {
		this.name = "";
		this.kollektorTemp = undefined;
		this.tartalyTemp = undefined;
		this.keringteto = undefined;
		this.futopatron = undefined;
	}
};

window.KollektorKontroller = KollektorKontroller;

var Kollektor = window.Kollektor || class {
	constructor() {
		this.historic = undefined;
		this.isDimmer = false;
	}
};

window.Kollektor = Kollektor;

class KollektorPatron {
	constructor() {
		this.historic=undefined;
		this.isDimmer=false;
	}
}
class keringteto {
	constructor() {
		this.historic=undefined;
		this.isDimmer=false;
	}
}
class futopatron {
	constructor() {
		this.historic=undefined;
		this.isDimmer=false;
	}
}
Date.prototype.yyyymmdd_hhmm = function() {
	var month = this.getMonth() + 1; // getMonth() is zero-based
	var dd = this.getDate();
	var hh = this.getHours();
	var minutes = this.getMinutes();

	return [this.getFullYear(),
		(month>9 ? '' : '0') + month,
		(dd>9 ? '' : '0') + dd,
		'_',
		(hh>9 ? '' : '0') + hh,
		(minutes>9 ? '' : '0') + minutes
		].join('');
};

function getRequestParam(name){
	var req = location.search;
	if(req.length == 0) {
		req = location.href;
	}
	if(name=(new RegExp('[?&]'+encodeURIComponent(name)+'=([^&]*)')).exec(req))
		return decodeURIComponent(name[1]);
}
function getKollektor() {
	nodata = true;
	var request=proto+address + ":" + port.toString() + hardwareReq;
	var kollektors = [];
	$.ajax({url: request,
		async: false,
		success: function(result){
			for(i=0;i<result.result.length;i++) {
				if(result.result[i].Extra == "NkV" && result.result[i].Enabled == "true") {
					nodata = false;
					var kollektor = new Kollektor();
					var keringteto=[];
					var futopatron=[];
					var tempOut = undefined;
					var tempInIdxs = result.result[i].Mode1.split(',');
					var tartalyTempIdx = result.result[i].Mode2;
					var keringtetoIdxs = result.result[i].Mode3.split(',');
					var patronIdxs = result.result[i].Mode4.split(',');
					var name = result.result[i].Name;
					kollektor.name = name;
					kollektor.id = result.result[i].idx;
					var minDate = Date.now() - (24 * 60 * 60 * 1000);
					var innerRequest = proto + address + ":" + port.toString() + devicesReq;
					$.ajax({
						url: innerRequest,
						async: false,
						success: function (resultKollektor) {
							kollektor.host = result.result[i].Address
							kollektor.uname = result.result[i].Username
							kollektor.pass = result.result[i].Password
							kollektor.port = result.result[i].Port
							kollektor.Mode1 = result.result[i].Mode1;
							kollektor.Mode2 = result.result[i].Mode2;
							kollektor.Mode3 = result.result[i].Mode3;
							kollektor.Mode4 = result.result[i].Mode4;
							kollektor.Mode5 = result.result[i].Mode5;
							kollektor.Mode6 = result.result[i].Mode6;
							//console.log(kollektor.Mode1);
							//console.log(kollektor.Mode6);
							}
						});

					request = proto + address + ":" + port.toString() + devicesReq;
					$.ajax({
						url: request,
						async: false,
						success: function(resultDevice) {
							for (var j = 0; j < resultDevice.result.length; j++) {

								var device = resultDevice.result[j];

								if (kollektor.id == device.HardwareID) {
									if (device.Unit == 6) {
										// Kollektor hőmérséklet
										request = proto + address + ":" + port.toString() + tempReq + device.idx;
										$.ajax({
											url: request,
											async: false,
											success: function(resultTempKollektor) {
												kollektor.kollektorTemp = resultTempKollektor.result;
											}
										});
									} else if (device.Unit == 7) {
										// Tartály hőmérséklet
										request = proto + address + ":" + port.toString() + tempReq + device.idx;
										$.ajax({
											url: request,
											async: false,
											success: function(resultTempTartaly) {
												kollektor.tartalyTemp = resultTempTartaly.result;
											}
										});
									} else if (device.Unit == 8) {
										// Keringtető
										if (!kollektor.keringteto) {
											kollektor.keringteto = new Kollektor();
										}

										request = proto + address + ":" + port.toString() + switchReq + device.idx;
										$.ajax({
											url: request,
											async: false,
											success: function(resultTemp) {
												var historic = (resultTemp && Array.isArray(resultTemp.result)) ? resultTemp.result : [];

												kollektor.keringteto.historic = historic
													.filter(item => new Date(item.Date).getTime() >= minDate)
													.sort((a, b) => new Date(a.Date) - new Date(b.Date));
											}
										});
									} else if (device.Unit == 9) {
										// Fűtőpatron
										if (!kollektor.futopatron) {
											kollektor.futopatron = new Kollektor();
										}

										requestpatron = proto + address + ":" + port.toString() + switchReq + device.idx;
										$.ajax({
											url: requestpatron,
											async: false,
											success: function(resultTempPatron) {
												var historic = (resultTempPatron && Array.isArray(resultTempPatron.result)) ? resultTempPatron.result : [];

												kollektor.futopatron.historic = historic
													.filter(item => new Date(item.Date).getTime() >= minDate)
													.sort((a, b) => new Date(a.Date) - new Date(b.Date));
											}
										});
									}
								}
							}
						}
					});

					var request = proto + address + ":" + port.toString() + tempName;
						$.ajax({
							url: request,
							async: false,
							success: function (resultTempName) {
								kollektor.tempnameakt = [];
								resultTempName.result.forEach(function (item) {
									if (item.Type.toLowerCase().includes('temp') &&
										item.Used === 1 &&
										(
											item.HardwareName.toLowerCase().includes('dummy') ||
											item.HardwareName.toLowerCase().includes('zigbee')
										)
								) {
										kollektor.tempnameakt.push(item.Name + ':' + item.idx);
									}
								});
								//console.log(resultTempName);
								//console.log(kollektor.tempnameakt);
							}
						});
						request = proto + address + ":" + port.toString() + switchName;
						$.ajax({
							url: request,
							async: false,
							success: function (resultswitchName) {
								kollektor.switchnameakt = [];
								resultswitchName.result.forEach(function (item) {
									if (
										item.SwitchType &&
										item.SwitchType.toLowerCase().includes('on/off') &&
										item.Used == 1
									) {
										kollektor.switchnameakt.push(item.Name + ':' + item.idx);
									}
								});
								//console.log(resultswitchName);
								//console.log(kollektor.switchnameakt);
							}
						});
					request=proto+address + ":" + port.toString() + devicesReq;
					$.ajax({url: request,
						async: false,
						success: function(resultTemp){
							for(var j=0;j<resultTemp.result.length;j++) {
								if(kollektor.id == resultTemp.result[i].HardwareID && resultTemp.result[i].Unit == 4) {
									request=proto+address + ":" + port.toString() + tempReq + resultTemp.result[i].idx;
									$.ajax({url: request,
										async: false,
										success: function(resultTemp2){
											//console.log(resultTemp2);
											kollektor.setpoint = resultTemp2.result;
										}
									});
								}
							}
						}
					});
					kollektors.push(kollektor);
				}
			}
			//console.log(kollektors);
		}
	});
	return kollektors;
}

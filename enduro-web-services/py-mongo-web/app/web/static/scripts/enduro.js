function createCell(row, cell_data) {
    
    var cell = row.insertCell();
    cell.appendChild(document.createTextNode(cell_data.toString()));
    return row;
};

// Reference: http://www.javascriptkit.com/script/script2/mps.shtml
function mpsToMph(speed) {

    var calculated = Math.round(speed * 3600 / 1610.3*1000)/1000;
    return calculated
};

// Reference: https://stackoverflow.com/questions/1322732/convert-seconds-to-hh-mm-ss-with-javascript
function secondsToIso(seconds) {

    if (seconds == 'DNF') {
        return 'DNF'
    } else {
        var converted = new Date(seconds * 1000).toISOString().substr(11, 8);
        return converted;
    }
}

window.onload=function () {

    $.getJSON('https://sideline.rastahorn.com/api/results', function(data) {
        console.log(data);

        var tbl_body = document.createElement("tbody");
        var header_row = tbl_body.insertRow();

        header_cells = ["First Name", "Last Name", "M/F", "Average Speed",
                        "Max Speed", "Total Move Time",
                        "Total Elapsed Time", "Seg 1 Move Time", "Seg 1 Elapsed Time",
                        "Seg 2 Move Time", "Seg 2 Elapsed Time", "Seg 3 Move Time", "Seg 3 Elapsed Time",
                        "Seg 4 Move Time", "Seg 4 Elapsed Time"
                        ]
        for (header_cell in header_cells) {
            cell = header_row.insertCell();
            cell.appendChild(document.createTextNode(header_cells[header_cell]));
        };

        $.each(data, function() {
            var tbl_row = tbl_body.insertRow();
            createCell(tbl_row, this['ath_fname']);
            createCell(tbl_row, this['ath_lname']);
            createCell(tbl_row, this['ath_sex']);

            var average_mph = mpsToMph(this['race_average_speed']);
            var max_mph = mpsToMph(this['race_max_speed']);
            createCell(tbl_row, average_mph);
            createCell(tbl_row, max_mph);

            var move_time = secondsToIso(this['race_move_time']);
            var total_time = secondsToIso(this['race_total_time']);
            createCell(tbl_row, move_time);
            createCell(tbl_row, total_time);

           $("#results_table").append(tbl_body);
        });
    });

}
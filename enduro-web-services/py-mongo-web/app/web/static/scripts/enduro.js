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

    if (seconds == 'DNF' || seconds == null) {
        return 'DNF'
    } else {
        var converted = new Date(seconds * 1000).toISOString().substr(11, 8);
        return converted;
    }
}

window.onload=function () {
    if($("#results-table").length > 0) {
        $.getJSON('https://sideline.rastahorn.com/api/results', function(data) {
            console.log(data);


            var tbl_head = document.createElement("thead");
            var header_row = tbl_head.insertRow();

            header_cells = ["First", "Last", "M/F", "Place", "Av. Speed", "Max Speed",
                            "Total Time", "Difference",
                            "Seg 1", "Seg 2", "Seg 3", "Seg 4"
                            ]

            for (header_cell in header_cells) {
                cell = header_row.insertCell();
                cell.appendChild(document.createTextNode(header_cells[header_cell]));
            };
            $("#results-table").append(tbl_head);

            var tbl_body = document.createElement("tbody");

            $.each(data, function() {
                var tbl_row = tbl_body.insertRow();
                createCell(tbl_row, this['ath_fname']);
                createCell(tbl_row, this['ath_lname']);
                createCell(tbl_row, this['ath_sex']);
                createCell(tbl_row, this['race_overall_place'])

                var average_mph = mpsToMph(this['activity_average_speed']);
                var max_mph = mpsToMph(this['activity_max_speed']);
                createCell(tbl_row, average_mph);
                createCell(tbl_row, max_mph);

                var move_time = secondsToIso(this['race_move_time']);
                var race_time_behind = secondsToIso(this['race_time_behind']);
                createCell(tbl_row, move_time);
                createCell(tbl_row, race_time_behind);

                var seg_0_move_time = secondsToIso(this['race_segment_0_moving']);
                var seg_1_move_time = secondsToIso(this['race_segment_1_moving']);
                var seg_2_move_time = secondsToIso(this['race_segment_2_moving']);
                var seg_3_move_time = secondsToIso(this['race_segment_3_moving']);
                createCell(tbl_row, seg_0_move_time);
                createCell(tbl_row, seg_1_move_time);
                createCell(tbl_row, seg_2_move_time);
                createCell(tbl_row, seg_3_move_time);

            $("#results-table").append(tbl_body);
            });
        });
    };
};
importScripts("https://unpkg.com/papaparse@5.4.1/papaparse.min.js");

self.onmessage = function (e) {
    const { url, options } = e.data;

    // Default column names to look for
    const latCols = ['lat', 'latitude', 'LAT', 'Latitude', 'y'];
    const lonCols = ['lon', 'lng', 'longitude', 'LON', 'Longitude', 'x'];
    const valCols = ['value', 'count', 'intensity', 'magnitude', 'mag'];

    Papa.parse(url, {
        download: true,
        header: true,
        dynamicTyping: true,
        skipEmptyLines: true,
        chunkSize: 1024 * 512, // 512KB chunks
        chunk: function (results) {
            const points = [];
            const data = results.data;

            if (data.length === 0) return;

            // Detect columns on first chunk if not provided
            // (Simpler: just check every row or first row of chunk)
            const firstRow = data[0];
            let foundLat = latCols.find(c => firstRow.hasOwnProperty(c));
            let foundLon = lonCols.find(c => firstRow.hasOwnProperty(c));
            let foundVal = valCols.find(c => firstRow.hasOwnProperty(c));

            for (let i = 0; i < data.length; i++) {
                const row = data[i];
                // Use detected columns or fallback
                // We re-detect per chunk safer? No, usually consistent. 
                // But simplified logic:

                let lat = row[foundLat];
                let lon = row[foundLon];
                let val = foundVal ? row[foundVal] : 1.0; // Default weight 1

                if (typeof lat === 'number' && typeof lon === 'number') {
                    // [lat, lng, intensity]
                    points.push([lat, lon, val]);
                }
            }

            if (points.length > 0) {
                self.postMessage({
                    type: 'chunk',
                    points: points
                });
            }
        },
        complete: function () {
            self.postMessage({ type: 'complete' });
        },
        error: function (err) {
            self.postMessage({ type: 'error', error: err });
        }
    });
};

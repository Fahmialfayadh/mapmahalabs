// Map Initialization
// ============================

// Initialize map with Surabaya coordinates
const map = L.map('map', {
    zoomControl: false,
    attributionControl: true
}).setView([-7.30, 112.74], 11);

// Move zoom control to bottom right (avoid sidebar overlap)
L.control.zoom({ position: 'bottomright' }).addTo(map);

// ============================
// Global UI Elements & State
// ============================
const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('sidebarOverlay');
const menuBtn = document.getElementById('menuBtn');

const correlationState = {
    layers: [],           // All available choropleth layers
    layerMetadata: {},    // Cached metadata (folder -> {type, name})
    layer1: null,
    layer2: null
};

// ============================
// Weather Layer Variables (declared early for inline handlers)

// ============================
var weatherLayers = {};
var weatherMarkerLayers = {};
var weatherTimeLabels = [];           // Store time labels for display
var weatherDataCache = {};            // Cache weather data for click interactions
var currentWeatherHourIndex = 0;      // Current hour index for weather display
var countriesGeoJSONCache = null;     // Cache countries GeoJSON (fetch once)
var countryCentroidsCache = {};       // Pre-calculated country centroids
var weatherColorScales = {
    temperature_2m: { colors: ['#313695', '#4575b4', '#74add1', '#abd9e9', '#fee090', '#fdae61', '#f46d43', '#d73027', '#a50026'], min: -20, max: 45, name: 'Suhu Udara', unit: '°C' },
    relative_humidity_2m: { colors: ['#fff5eb', '#fee6ce', '#fdd0a2', '#fdae6b', '#fd8d3c', '#f16913', '#d94801', '#a63603', '#7f2704'], min: 0, max: 100, name: 'Kelembaban', unit: '%' },
    precipitation: { colors: ['#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b'], min: 0, max: 50, name: 'Curah Hujan', unit: 'mm' },
    wind_speed_10m: { colors: ['#f7fcf5', '#e5f5e0', '#c7e9c0', '#a1d99b', '#74c476', '#41ab5d', '#238b45', '#006d2c', '#00441b'], min: 0, max: 60, name: 'Kecepatan Angin', unit: 'km/h' },
    cloud_cover: { colors: ['#fff5f0', '#fee0d2', '#fcbba1', '#fc9272', '#fb6a4a', '#ef3b2c', '#cb181d', '#a50f15', '#67000d'], min: 0, max: 100, name: 'Tutupan Awan', unit: '%' },
    surface_pressure: { colors: ['#fcfbfd', '#efedf5', '#dadaeb', '#bcbddc', '#9e9ac8', '#807dba', '#6a51a3', '#54278f', '#3f007d'], min: 990, max: 1030, name: 'Tekanan Udara', unit: 'hPa' },
    uv_index: { colors: ['#4a1486', '#6a51a3', '#807dba', '#9e9ac8', '#bcbddc', '#fee391', '#fec44f', '#fe9929', '#d95f0e', '#993404'], min: 0, max: 12, name: 'Indeks UV', unit: '' }
};

// Weather color function
function getWeatherColor(value, variable) {
    const scale = weatherColorScales[variable] || weatherColorScales.temperature_2m;
    const { colors, min, max } = scale;
    const ratio = Math.max(0, Math.min(1, (value - min) / (max - min)));
    const index = Math.min(Math.floor(ratio * (colors.length - 1)), colors.length - 1);
    return colors[index];
}

// ============================
// Color Schemes for Heatmap
// ============================
const colorSchemes = {
    ylorrd: {
        colors: ['#FFEDA0', '#FEB24C', '#FD8D3C', '#FC4E2A', '#E31A1C', '#BD0026', '#800026'],
        gradient: 'linear-gradient(to right, #FFEDA0, #FEB24C, #FD8D3C, #FC4E2A, #E31A1C, #BD0026, #800026)'
    },
    blues: {
        colors: ['#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6', '#3182bd', '#08519c'],
        gradient: 'linear-gradient(to right, #f7fbff, #deebf7, #c6dbef, #9ecae1, #6baed6, #3182bd, #08519c)'
    },
    greens: {
        colors: ['#f7fcf5', '#e5f5e0', '#c7e9c0', '#a1d99b', '#74c476', '#31a354', '#006d2c'],
        gradient: 'linear-gradient(to right, #f7fcf5, #e5f5e0, #c7e9c0, #a1d99b, #74c476, #31a354, #006d2c)'
    },
    purples: {
        colors: ['#fcfbfd', '#efedf5', '#dadaeb', '#bcbddc', '#9e9ac8', '#756bb1', '#54278f'],
        gradient: 'linear-gradient(to right, #fcfbfd, #efedf5, #dadaeb, #bcbddc, #9e9ac8, #756bb1, #54278f)'
    },
    viridis: {
        colors: ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725'],
        gradient: 'linear-gradient(to right, #440154, #482878, #3e4989, #31688e, #26828e, #1f9e89, #35b779, #6ece58, #b5de2b, #fde725)'
    },
    plasma: {
        colors: ['#0d0887', '#46039f', '#7201a8', '#9c179e', '#bd3786', '#d8576b', '#ed7953', '#fb9f3a', '#fdca26', '#f0f921'],
        gradient: 'linear-gradient(to right, #0d0887, #46039f, #7201a8, #9c179e, #bd3786, #d8576b, #ed7953, #fb9f3a, #fdca26, #f0f921)'
    }
};

// Store selected color scheme per layer
const layerColorSchemes = {};

function getColor(d, maxVal, scheme = 'ylorrd') {
    // Cegah pembagian dengan 0
    const colors = colorSchemes[scheme]?.colors || colorSchemes.ylorrd.colors;
    if (maxVal === 0) return colors[0];

    const ratio = d / maxVal;
    const numColors = colors.length;

    // Calculate which color bucket based on ratio
    if (numColors === 7) {
        // Standard 7-color schemes
        return ratio > 0.857 ? colors[6] :
            ratio > 0.714 ? colors[5] :
                ratio > 0.571 ? colors[4] :
                    ratio > 0.428 ? colors[3] :
                        ratio > 0.285 ? colors[2] :
                            ratio > 0.142 ? colors[1] :
                                colors[0];
    } else {
        // 10-color schemes (viridis, plasma)
        return ratio > 0.9 ? colors[9] :
            ratio > 0.8 ? colors[8] :
                ratio > 0.7 ? colors[7] :
                    ratio > 0.6 ? colors[6] :
                        ratio > 0.5 ? colors[5] :
                            ratio > 0.4 ? colors[4] :
                                ratio > 0.3 ? colors[3] :
                                    ratio > 0.2 ? colors[2] :
                                        ratio > 0.1 ? colors[1] :
                                            colors[0];
    }
}

// Update legend gradient based on color scheme
function updateLegendGradient(scheme) {
    const legendGradient = document.getElementById('legendGradient');
    if (legendGradient && colorSchemes[scheme]) {
        legendGradient.style.background = colorSchemes[scheme].gradient;
    }
}
// ============================
// Basemap Definitions
// ============================

const basemaps = {
    osm: L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19
    }),
    satellite: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: '&copy; Esri',
        maxZoom: 18
    }),
    topo: L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenTopoMap',
        maxZoom: 17
    }),
    dark: L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; CartoDB',
        maxZoom: 19
    })
};
// Basemap event listeners are now handled via switchBasemap logic and individual button clicks
// Initial listener setup
document.querySelectorAll('.basemap-btn').forEach(btn => {
    btn.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        const key = btn.dataset.basemap;
        switchBasemap(key);
    });
});

// Set default basemap
const activeBtn = document.querySelector('.basemap-btn.active-basemap');
// Default to 'osm' (Light) if no active button, or if active button says so
const defaultKey = activeBtn ? activeBtn.dataset.basemap : 'osm';

let currentBasemap = basemaps[defaultKey];
if (currentBasemap) {
    currentBasemap.addTo(map);
    // Ensure we start with correct UI state if defaulting
    if (!activeBtn) {
        document.querySelectorAll('.basemap-btn[data-basemap="osm"]').forEach(btn => {
            btn.classList.add('active-basemap', 'border-blue-500', 'bg-blue-50', 'text-blue-700');
            btn.classList.remove('border-gray-200', 'bg-white', 'text-gray-600');
        });
    }
}

// Function to switch basemap programmatically
function switchBasemap(key) {
    if (!basemaps[key]) return;

    // Update map layer
    if (currentBasemap) map.removeLayer(currentBasemap);
    currentBasemap = basemaps[key];
    currentBasemap.addTo(map);
    currentBasemap.bringToBack();

    // Update UI buttons
    document.querySelectorAll('.basemap-btn').forEach(btn => {
        if (btn.dataset.basemap === key) {
            btn.classList.add('active-basemap', 'border-blue-500', 'bg-blue-50', 'text-blue-700');
            btn.classList.remove('border-gray-200', 'bg-white', 'text-gray-600');
        } else {
            btn.classList.remove('active-basemap', 'border-blue-500', 'bg-blue-50', 'text-blue-700');
            btn.classList.add('border-gray-200', 'bg-white', 'text-gray-600');
        }
    });
}

// Listen for theme changes from index.html
document.addEventListener('themeChanged', function (e) {
    console.log('Theme changed event received:', e.detail);
    if (e.detail.theme === 'dark') {
        switchBasemap('dark');
    } else {
        switchBasemap('osm');
    }
});

// ============================
// Layer Management
// ============================

// Base URL for storage (injected from Flask template via APP_CONFIG)
const storageBaseUrl = window.APP_CONFIG?.storageUrl || "";

// Active overlay layers
let activeLayers = {};

// ============================
// Deep Linking Logic
// ============================
function updateUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const activeLayerIds = [];

    // Collect active layers
    document.querySelectorAll('.layer-toggle:checked').forEach(toggle => {
        // Use folder name as ID (slug)
        activeLayerIds.push(toggle.dataset.folder);
    });

    if (activeLayerIds.length > 0) {
        params.set('layers', activeLayerIds.join(','));
    } else {
        params.delete('layers');
    }

    // Update URL without reloading
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', newUrl);
}

function loadFromUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const layersParam = params.get('layers');

    if (layersParam) {
        const layerIds = layersParam.split(',');
        layerIds.forEach(id => {
            const toggle = document.querySelector(`.layer-toggle[data-folder="${id}"]`);
            if (toggle && !toggle.checked) {
                toggle.checked = true;
                // Trigger change event manually - MUST bubble for delegation to work
                toggle.dispatchEvent(new Event('change', { bubbles: true }));

                // Expand card visually
                const card = toggle.closest('.layer-card');
                if (card) card.classList.add('expanded');
            }
        });
    }
}

// ============================
// Event Handlers (using event delegation for dynamic layers)
// ============================

// Layer toggle functionality - using event delegation
// Pastikan fungsi getColor sudah ada di paling atas script (di luar event listener)
// function getColor(d, maxVal) { ... }

// Accordion Toggle Function
// Accordion Toggle Function (Modified for Insight Layers)
function toggleLayerDetail(element, event) {
    // Check if we clicked on the switch (handled by stopPropagation, but double check)
    if (event.target.closest('.layer-toggle') || event.target.closest('.toggle-switch') || event.target.closest('a')) {
        return;
    }


    // Default behavior: Toggle the expanded class
    const card = element.closest('.layer-card');
    if (card) {
        card.classList.toggle('expanded');
    } else {
        element.classList.toggle('expanded');
    }
}

// Tab Switching Logic
document.addEventListener('DOMContentLoaded', () => {
    const tabs = document.querySelectorAll('.tab-btn');
    const contents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetId = tab.dataset.tab;

            // Update Tabs
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Update Content
            contents.forEach(c => {
                c.classList.remove('active');
                c.classList.add('hidden');
                if (c.id === targetId) {
                    c.classList.remove('hidden');
                    // Small delay to allow display:block to apply before opacity transition
                    setTimeout(() => c.classList.add('active'), 10);

                    // Re-initialize features based on tab
                    if (targetId === 'analysis-tab') {
                        console.log('Switching to Analysis tab, reinforcing correlation init...');
                        initCorrelationFeature();
                    }
                }
            });
        });
    });

    // Load state from URL
    loadFromUrlParams();
});

document.getElementById('layersList').addEventListener('change', async function (e) {
    if (!e.target.classList.contains('layer-toggle')) return;

    const toggle = e.target;
    const folder = toggle.dataset.folder;
    const layerType = toggle.dataset.type || 'tiles';
    const opacitySlider = document.getElementById('opacitySlider');
    const opacity = opacitySlider ? parseFloat(opacitySlider.value) : 1.0;

    console.log(`Toggle layer: ${folder}, type: ${layerType}, checked: ${toggle.checked}`);

    if (toggle.checked) {
        // --- LOGIKA MENAMBAHKAN LAYER ---
        if (layerType === 'choropleth') {
            // === CHOROPLETH LAYER ===
            try {
                console.log('Loading choropleth layer...');

                // 1. Initial Fetch to get Metadata
                const choroplethRes = await fetch(`/api/choropleth-data/${folder}`);
                if (!choroplethRes.ok) throw new Error('Failed to load choropleth data');
                const choroplethData = await choroplethRes.json();

                console.log('Choropleth data:', choroplethData);

                // 2. Load Geometry (Countries or Custom Points)
                let countriesRes;
                if (choroplethData.geojson_file) {
                    // Use custom geometry (e.g. for Province Heatmap)
                    const geoUrl = `/api/layer-geometry/${folder}/${choroplethData.geojson_file}`;
                    console.log(`Loading custom geometry: ${geoUrl}`);
                    countriesRes = await fetch(geoUrl);
                } else {
                    // Default to World Countries
                    countriesRes = await fetch('/api/countries-geojson');
                }

                if (!countriesRes.ok) throw new Error('Failed to load geometry');
                const countriesGeoJSON = await countriesRes.json();

                console.log('Choropleth data:', choroplethData);

                // 2. Setup year slider
                const years = choroplethData.years || ['all'];
                const hasYears = years.length > 1 || years[0] !== 'all';

                if (hasYears) {
                    const yearSlider = document.getElementById('yearSlider');
                    const yearDisplay = document.getElementById('yearDisplay');
                    const yearMin = document.getElementById('yearMin');
                    const yearMax = document.getElementById('yearMax');

                    yearSlider.min = 0;
                    yearSlider.max = years.length - 1;
                    yearSlider.value = years.length - 1; // Start at latest year
                    yearDisplay.textContent = years[years.length - 1];
                    yearMin.textContent = years[0];
                    yearMax.textContent = years[years.length - 1];

                    document.getElementById('yearSliderContainer').classList.add('active');
                }

                // 3. Setup legend
                // 3. Setup legend
                let title = choroplethData.value_column || 'Value';
                // Clean up title: remove parentheses content if distinct, e.g. "GDP (USD)" -> "GDP"
                if (title.length > 25 && title.includes('(')) {
                    title = title.split('(')[0].trim();
                }
                // Replace underscores
                title = title.replace(/_/g, ' ');

                document.getElementById('legendTitle').textContent = title;

                const maxVal = choroplethData.max_value;
                const minVal = choroplethData.min_value;

                document.getElementById('legendMin').textContent = formatNumber(minVal);
                document.getElementById('legendMax').textContent = formatNumber(maxVal);

                // Intermediate values
                document.getElementById('legendMed').textContent = formatNumber((minVal + maxVal) / 2);
                document.getElementById('legendQ1').textContent = formatNumber(minVal + (maxVal - minVal) * 0.25);
                document.getElementById('legendQ3').textContent = formatNumber(minVal + (maxVal - minVal) * 0.75);

                document.getElementById('legendContainer').classList.add('active');

                // Set initial color scheme for this layer
                if (!layerColorSchemes[folder]) {
                    layerColorSchemes[folder] = 'ylorrd';
                }
                const currentScheme = layerColorSchemes[folder];
                updateLegendGradient(currentScheme);

                // 4. Create choropleth layer
                const currentYear = hasYears ? years[years.length - 1] : 'all';

                const choroplethLayer = L.geoJSON(countriesGeoJSON, {
                    // Support for Points (CircleMarkers) - Heatmap Style
                    pointToLayer: (feature, latlng) => {
                        const countryCode = feature.properties['ISO3166-1-Alpha-3'] ||
                            feature.properties['ISO3166-1-Alpha-2'] ||
                            feature.properties.name;
                        const countryData = choroplethData.data[countryCode] ||
                            choroplethData.data[countryCode?.toUpperCase()];
                        const value = countryData ? (countryData[currentYear] || 0) : null;

                        // Dynamic Radius based on value relative to max
                        const maxVal = choroplethData.max_value || 100;
                        const radius = value !== null ? Math.max(5, (Math.sqrt(value) / Math.sqrt(maxVal)) * 25) : 5;

                        return L.circleMarker(latlng, {
                            radius: radius,
                            fillColor: value !== null ? getColor(value, choroplethData.max_value, layerColorSchemes[folder] || 'ylorrd') : '#ccc',
                            color: '#fff',
                            weight: 1,
                            opacity: 1,
                            fillOpacity: 0.8
                        });
                    },
                    style: (feature) => {
                        // Only applies to Polygons/Lines
                        const countryCode = feature.properties['ISO3166-1-Alpha-3'] ||
                            feature.properties['ISO3166-1-Alpha-2'] ||
                            feature.properties['Propinsi'] ||
                            feature.properties.name;
                        const countryData = choroplethData.data[countryCode] ||
                            choroplethData.data[countryCode?.toUpperCase()];
                        const value = countryData ? (countryData[currentYear] || 0) : null;

                        return {
                            fillColor: value !== null ? getColor(value, choroplethData.max_value, layerColorSchemes[folder] || 'ylorrd') : '#ccc',
                            weight: 0.5,
                            opacity: 1,
                            color: '#e21515',
                            fillOpacity: value !== null ? 0.7 : 0.3
                        };
                    },
                    onEachFeature: (feature, layer) => {
                        const countryCode = feature.properties['ISO3166-1-Alpha-3'] ||
                            feature.properties['ISO3166-1-Alpha-2'] ||
                            feature.properties['Propinsi'];
                        const countryName = feature.properties.name || feature.properties['Propinsi'] || countryCode;
                        const countryData = choroplethData.data[countryCode] ||
                            choroplethData.data[countryCode?.toUpperCase()];
                        const value = countryData ? (countryData[currentYear] || 0) : null;

                        let popup = `<div class="text-country"><b style="font-size: 12px; color: #ffffffff">${countryName}</b><br>`;
                        if (value !== null) {
                            popup += `${choroplethData.value_column}: ${formatNumber(value)}`;
                        } else {
                            popup += '<i>No data</i>';
                        }
                        popup += '</div>';
                        layer.bindPopup(popup);
                    }
                }).addTo(map);

                // Store layer with metadata
                activeLayers[folder] = {
                    layer: choroplethLayer,
                    type: 'choropleth',
                    data: choroplethData,
                    years: years
                };

                // 5. Year slider event handler
                if (hasYears) {
                    const yearSlider = document.getElementById('yearSlider');
                    const yearDisplay = document.getElementById('yearDisplay');
                    const playBtn = document.getElementById('playBtn');
                    let playInterval = null;

                    // Helper to update layer
                    const updateLayer = (index) => {
                        const selectedYear = years[index];
                        yearDisplay.textContent = selectedYear;

                        choroplethLayer.eachLayer((layer) => {
                            const feature = layer.feature;
                            const countryCode = feature.properties['ISO3166-1-Alpha-3'] ||
                                feature.properties['ISO3166-1-Alpha-2'] ||
                                feature.properties['Propinsi'];
                            const countryData = choroplethData.data[countryCode] ||
                                choroplethData.data[countryCode?.toUpperCase()];
                            const value = countryData ? (countryData[selectedYear] || 0) : null;
                            const countryName = feature.properties.name || feature.properties['Propinsi'] || countryCode;

                            const color = value !== null ? getColor(value, choroplethData.max_value, layerColorSchemes[folder] || 'ylorrd') : '#ccc';

                            // Handle Point Layers (CircleMarker)
                            if (layer instanceof L.CircleMarker) {
                                const maxVal = choroplethData.max_value || 100;
                                const radius = value !== null ? Math.max(5, (Math.sqrt(value) / Math.sqrt(maxVal)) * 25) : 5;

                                layer.setStyle({
                                    fillColor: color,
                                    fillOpacity: 0.8,
                                    radius: radius
                                });
                            } else {
                                // Handle Polygon Layers
                                layer.setStyle({
                                    fillColor: color,
                                    fillOpacity: value !== null ? 0.7 : 0.3
                                });
                            }

                            // Update popup
                            let popup = `<div class="text-country"><b style="font-size: 12px; color: #ffffffff">${countryName}</b><br>`;
                            if (value !== null) {
                                popup += `${choroplethData.value_column}: ${formatNumber(value)}`;
                            } else {
                                popup += '<i>No data</i>';
                            }
                            popup += '</div>';
                            layer.setPopupContent(popup);
                        });
                    };

                    // Manual Interaction
                    yearSlider.oninput = function () {
                        // Stop animation on manual drag
                        if (playInterval) togglePlay();
                        updateLayer(this.value);
                        // Update ranking for selected year
                        updateRankingPanel(folder, choroplethData, years[this.value]);
                    };

                    // Play/Pause Function
                    const togglePlay = () => {
                        if (playInterval) {
                            clearInterval(playInterval);
                            playInterval = null;
                            playBtn.classList.remove('playing');
                            playBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>'; // Play Icon
                        } else {
                            playBtn.classList.add('playing');
                            playBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>'; // Pause Icon

                            playInterval = setInterval(() => {
                                let nextVal = parseInt(yearSlider.value) + 1;
                                if (nextVal >= years.length) {
                                    nextVal = 0; // Loop back to start
                                }
                                yearSlider.value = nextVal;
                                updateLayer(nextVal);
                                // Update ranking during animation
                                updateRankingPanel(folder, choroplethData, years[nextVal]);
                            }, 800); // 800ms per frame
                        }
                    };

                    // Remove existing listener to prevent duplicates if layer re-toggled
                    const newPlayBtn = playBtn.cloneNode(true);
                    playBtn.parentNode.replaceChild(newPlayBtn, playBtn);
                    newPlayBtn.addEventListener('click', togglePlay);
                }

                // Fit bounds to world view
                map.fitBounds([[-60, -180], [85, 180]]);

                // 6. Update ranking panel
                const initialYear = hasYears ? years[years.length - 1] : 'all';
                updateRankingPanel(folder, choroplethData, initialYear);

            } catch (err) {
                console.error('Error loading choropleth:', err);
                alert(`Gagal load choropleth: ${err.message}`);
                toggle.checked = false;
            }
        } else if (layerType === 'geojson') {
            try {
                const url = `/api/layer-data/${folder}`;
                console.log(`Fetching GeoJSON via proxy: ${url}`);
                const response = await fetch(url);

                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                const geojsonData = await response.json();
                console.log(`Loaded ${geojsonData.features?.length || 0} features`);

                // 1. Hitung Nilai Max untuk Skala Warna
                let calculatedMax = 0;
                geojsonData.features.forEach(f => {
                    let val = 0;
                    const p = f.properties;
                    if (p.GDP) val = parseFloat(p.GDP);
                    else if (p['GDP per capita, PPP (constant 2021 international $)']) val = parseFloat(p['GDP per capita, PPP (constant 2021 international $)']);
                    else if (p.Value) val = parseFloat(p.Value);
                    else if (p.OBS_VALUE) val = parseFloat(p.OBS_VALUE);

                    if (val > calculatedMax) calculatedMax = val;
                });

                // Set initial color scheme for this layer
                if (!layerColorSchemes[folder]) {
                    layerColorSchemes[folder] = 'ylorrd';
                }

                // 2. Buat Layer GeoJSON
                const layer = L.geoJSON(geojsonData, {
                    pointToLayer: (feature, latlng) => {
                        let val = 0;
                        const p = feature.properties;
                        // Ambil nilai (sama logicnya dgn loop diatas)
                        if (p.GDP) val = parseFloat(p.GDP);
                        else if (p['GDP per capita, PPP (constant 2021 international $)']) val = parseFloat(p['GDP per capita, PPP (constant 2021 international $)']);
                        else if (p.Value) val = parseFloat(p.Value);
                        else if (p.OBS_VALUE) val = parseFloat(p.OBS_VALUE);

                        // Styling Dinamis
                        return L.circleMarker(latlng, {
                            // Radius responsif
                            radius: calculatedMax > 0 ? Math.min(Math.max((Math.sqrt(val) / Math.sqrt(calculatedMax)) * 20, 4), 30) : 5,
                            // Warna pakai calculatedMax dan color scheme
                            fillColor: getColor(val, calculatedMax, layerColorSchemes[folder] || 'ylorrd'),
                            color: '#fff',
                            weight: 1,
                            opacity: 1,
                            fillOpacity: 0.8
                        });
                    },
                    onEachFeature: (feature, layer) => {
                        if (feature.properties) {
                            let popupContent = '<div class="text-sm max-h-48 overflow-y-auto">';
                            for (const key in feature.properties) {
                                popupContent += `<b>${key}:</b> ${feature.properties[key]}<br>`;
                            }
                            popupContent += '</div>';
                            layer.bindPopup(popupContent);
                        }
                    }
                }).addTo(map);

                // 3. Simpan ke activeLayers dengan metadata
                activeLayers[folder] = {
                    layer: layer,
                    type: 'geojson',
                    maxValue: calculatedMax,
                    geojsonData: geojsonData
                };
                if (geojsonData.features && geojsonData.features.length > 0) {
                    map.fitBounds(layer.getBounds(), { padding: [50, 50] });
                }

            } catch (err) {
                console.error('Error loading GeoJSON:', err);
                alert(`Gagal load layer: ${err.message}`);
                toggle.checked = false;
            }
        } else {
            // --- LOGIKA TILES ---
            const layer = L.tileLayer(`${storageBaseUrl}/${folder}/{z}/{x}/{y}.png`, {
                tms: false,
                opacity: opacity,
                maxZoom: 18,
                minZoom: 0,
                maxNativeZoom: 12,
                errorTileUrl: ''
            }).addTo(map);

            console.log(`Added tile layer: ${folder}`);
            activeLayers[folder] = layer;
        }

    } else {
        // --- LOGIKA MENGHAPUS LAYER (UNCHECK) ---
        if (activeLayers[folder]) {
            const layerInfo = activeLayers[folder];
            if (layerInfo.type === 'choropleth') {
                map.removeLayer(layerInfo.layer);
                // Hide year slider and legend
                document.getElementById('yearSliderContainer').classList.remove('active');
                document.getElementById('legendContainer').classList.remove('active');
                // Hide ranking panel
                hideRankingPanel(folder);
            } else {
                map.removeLayer(layerInfo.layer || layerInfo);
                // Hide ranking for geojson layers too
                hideRankingPanel(folder);
            }
            delete activeLayers[folder];
        }
    }

    // Update URL parameters
    updateUrlParams();
});

// Helper function to format numbers
function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toFixed(0);
}

// ============================
// Ranking Panel Functions
// ============================

// Store ranking state
const rankingState = {
    rankings: [],
    currentCount: 10,
    year: 'all',
    folder: null,
    choroplethData: null,
    sortOrder: 'desc' // 'desc' (Top) or 'asc' (Bottom)
};

/**
 * Generate sorted ranking data from choropleth/geojson data
 */
function generateRankingData(choroplethData, year = 'all') {
    const data = choroplethData.data;
    const rankings = [];

    for (const regionCode in data) {
        const regionData = data[regionCode];
        const value = year !== 'all' ? (regionData[year] || 0) : Object.values(regionData)[0] || 0;

        if (value > 0) {
            rankings.push({
                code: regionCode,
                name: formatRegionName(regionCode),
                value: value
            });
        }
    }

    // Sort by value based on state
    rankings.sort((a, b) => {
        return rankingState.sortOrder === 'asc'
            ? a.value - b.value
            : b.value - a.value;
    });

    return rankings;
}

/**
 * Format region code to readable name
 */
function formatRegionName(code) {
    if (!code) return 'Unknown';

    // 1. Try lookup in global mapping (from pycountry)
    if (window.COUNTRY_MAPPING) {
        // Try exact match
        if (window.COUNTRY_MAPPING[code]) return window.COUNTRY_MAPPING[code];
        // Try uppercase (common for ISO codes)
        if (window.COUNTRY_MAPPING[code.toUpperCase()]) return window.COUNTRY_MAPPING[code.toUpperCase()];
    }

    // 2. Fallback: Title Case
    return code.split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(' ');
}

/**
 * Get position class for ranking badge
 */
function getPositionClass(position) {
    if (position === 1) return 'gold';
    if (position === 2) return 'silver';
    if (position === 3) return 'bronze';
    return 'normal';
}

/**
 * Generate ranking HTML for a slice of data
 */
function generateRankingHTML(rankings, startIndex, count) {
    const endIndex = Math.min(startIndex + count, rankings.length);
    let html = '';

    for (let i = startIndex; i < endIndex; i++) {
        const item = rankings[i];
        const position = i + 1;
        const positionClass = getPositionClass(position);

        html += `
            <div class="ranking-item" data-region="${item.code}">
                <span class="ranking-position ${positionClass}">${position}</span>
                <span class="ranking-name" title="${item.name}">${item.name}</span>
                <span class="ranking-value">${formatNumber(item.value)}</span>
            </div>
        `;
    }

    return html;
}

/**
 * Show and populate floating ranking panel
 */
function showRankingPanel(folder, choroplethData, year = 'all') {
    const container = document.getElementById('rankingContainer');
    const listEl = document.getElementById('rankingList');
    const titleEl = document.getElementById('rankingTitle'); // Add this
    const sortBtn = document.getElementById('rankingSortBtn'); // Add this
    const yearBadge = document.getElementById('rankingYearBadge');
    const moreBtn = document.getElementById('rankingMoreBtn');
    const remainingEl = document.getElementById('rankingRemaining');

    if (!container || !listEl) return;

    // Reset sort order to default (desc/Top) when switching layers
    // Note: if just updating year (same folder), we might want to keep sort order
    if (rankingState.folder !== folder) {
        rankingState.sortOrder = 'desc';
    }

    // Generate rankings
    const rankings = generateRankingData(choroplethData, year);

    // Store state
    rankingState.rankings = rankings;
    rankingState.currentCount = 10;
    rankingState.year = year;
    rankingState.folder = folder;
    rankingState.choroplethData = choroplethData;
    // sortOrder is already set above or preserved

    // Update UI for Sort Order
    if (titleEl) {
        titleEl.textContent = rankingState.sortOrder === 'desc' ? 'Top Ranking' : 'Bottom Ranking';
    }
    if (sortBtn) {
        if (rankingState.sortOrder === 'asc') {
            sortBtn.classList.add('asc');
        } else {
            sortBtn.classList.remove('asc');
        }
    }

    // Update year badge
    if (year !== 'all') {
        yearBadge.textContent = year;
        yearBadge.style.display = 'block';
    } else {
        yearBadge.style.display = 'none';
    }

    // Show container
    container.classList.add('active');

    // Generate initial HTML (top 10)
    const initialCount = Math.min(10, rankings.length);
    listEl.innerHTML = generateRankingHTML(rankings, 0, initialCount);

    // Update more button
    const remaining = rankings.length - initialCount;
    if (remaining > 0) {
        moreBtn.style.display = 'flex';
        remainingEl.textContent = `(${remaining} tersisa)`;
    } else {
        moreBtn.style.display = 'none';
    }
}

/**
 * Update ranking for new year (used by year slider)
 */
function updateRankingPanel(folder, choroplethData, year = 'all') {
    // Only update if ranking panel is for this folder
    if (rankingState.folder !== folder && rankingState.folder !== null) return;

    showRankingPanel(folder, choroplethData, year);
}

/**
 * Hide floating ranking panel
 */
function hideRankingPanel(folder) {
    const container = document.getElementById('rankingContainer');
    if (!container) return;

    // Only hide if this is the active folder
    if (rankingState.folder === folder) {
        container.classList.remove('active', 'expanded');
        rankingState.folder = null;
        rankingState.rankings = [];
    }
}

/**
 * Load +10 more ranking items
 */
function loadMoreRanking() {
    const listEl = document.getElementById('rankingList');
    const moreBtn = document.getElementById('rankingMoreBtn');
    const remainingEl = document.getElementById('rankingRemaining');

    if (!listEl || rankingState.rankings.length === 0) return;

    const startIndex = rankingState.currentCount;
    const addCount = 10;

    // Append new items
    const newHTML = generateRankingHTML(rankingState.rankings, startIndex, addCount);
    listEl.insertAdjacentHTML('beforeend', newHTML);

    // Update state
    rankingState.currentCount += addCount;

    // Update or hide more button
    const remaining = rankingState.rankings.length - rankingState.currentCount;
    if (remaining > 0) {
        remainingEl.textContent = `(${remaining} tersisa)`;
    } else {
        moreBtn.style.display = 'none';
    }
}

/**
 * Toggle Sort Order
 */
function toggleSortOrder() {
    // 1. Toggle state
    rankingState.sortOrder = rankingState.sortOrder === 'desc' ? 'asc' : 'desc';

    // 2. Refresh Ranking Data
    // We need to re-generate because the order changed completely
    if (rankingState.choroplethData) {
        rankingState.rankings = generateRankingData(rankingState.choroplethData, rankingState.year);
        rankingState.currentCount = 10; // Reset pagination
    }

    // 3. Update UI
    const listEl = document.getElementById('rankingList');
    const titleEl = document.getElementById('rankingTitle');
    const sortBtn = document.getElementById('rankingSortBtn');
    const moreBtn = document.getElementById('rankingMoreBtn');
    const remainingEl = document.getElementById('rankingRemaining');

    if (listEl) {
        // Clear list
        listEl.innerHTML = '';

        // Re-render top 10
        const initialCount = Math.min(10, rankingState.rankings.length);
        listEl.innerHTML = generateRankingHTML(rankingState.rankings, 0, initialCount);

        // Update Title
        if (titleEl) {
            titleEl.textContent = rankingState.sortOrder === 'desc' ? 'Top Ranking' : 'Bottom Ranking';
        }

        // Update Sort Button Icon/Class
        if (sortBtn) {
            if (rankingState.sortOrder === 'asc') {
                sortBtn.classList.add('asc');
            } else {
                sortBtn.classList.remove('asc');
            }
        }

        // Update More Button
        const remaining = rankingState.rankings.length - initialCount;
        if (remaining > 0) {
            moreBtn.style.display = 'flex';
            remainingEl.textContent = `(${remaining} tersisa)`;
        } else {
            moreBtn.style.display = 'none';
        }
    }
}

// Toggle ranking panel expand/collapse
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('rankingContainer');
    const toggleBtn = document.getElementById('rankingToggleBtn');
    const moreBtn = document.getElementById('rankingMoreBtn');
    const sortBtn = document.getElementById('rankingSortBtn');

    if (toggleBtn && container) { // Cek keduanya agar tidak error
        toggleBtn.addEventListener('click', () => {

            // 1. Toggle class untuk animasi container
            container.classList.toggle('expanded');

            // 2. (Opsional) Toggle class di tombolnya sendiri agar warna/icon berubah
            toggleBtn.classList.toggle('active');

            // 3. (Best Practice) Update atribut ARIA untuk aksesibilitas
            const isExpanded = container.classList.contains('expanded');
            toggleBtn.setAttribute('aria-expanded', isExpanded);
        });
    }

    if (moreBtn) {
        moreBtn.addEventListener('click', () => {
            loadMoreRanking();
        });
    }

    if (sortBtn) {
        sortBtn.addEventListener('click', () => {
            toggleSortOrder();
        });
    }

    // Click on ranking item -> highlight on map
    document.getElementById('rankingList')?.addEventListener('click', (e) => {
        const item = e.target.closest('.ranking-item');
        if (item) {
            const regionCode = item.dataset.region;
            console.log(`Clicked ranking: ${regionCode}`);
            // Could add fly-to or highlight functionality here
        }
    });
});

// ============================
// Color Scheme Picker Event Handler
// ============================
document.querySelectorAll('.color-scheme-picker').forEach(picker => {
    picker.addEventListener('click', (e) => {
        const btn = e.target.closest('.color-scheme-btn');
        if (!btn) return;

        const folder = picker.dataset.layerFolder;
        const newScheme = btn.dataset.scheme;

        // Update active button state
        picker.querySelectorAll('.color-scheme-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Store the new scheme
        layerColorSchemes[folder] = newScheme;

        // Update legend gradient if this layer's legend is visible
        updateLegendGradient(newScheme);

        // Check if this folder has an active layer and update it
        if (activeLayers[folder]) {
            const layerInfo = activeLayers[folder];

            if (layerInfo.type === 'choropleth') {
                // Update choropleth layer colors
                const choroplethData = layerInfo.data;
                const years = layerInfo.years || ['all'];
                const yearSlider = document.getElementById('yearSlider');
                const currentIndex = parseInt(yearSlider.value);
                const currentYear = years.length > 1 ? years[currentIndex] : 'all';

                layerInfo.layer.eachLayer((layer) => {
                    const feature = layer.feature;
                    const countryCode = feature.properties['ISO3166-1-Alpha-3'] ||
                        feature.properties['ISO3166-1-Alpha-2'] ||
                        feature.properties['Propinsi'];
                    const countryData = choroplethData.data[countryCode] ||
                        choroplethData.data[countryCode?.toUpperCase()];
                    const value = countryData ? (countryData[currentYear] || 0) : null;

                    const color = value !== null ? getColor(value, choroplethData.max_value, newScheme) : '#ccc';

                    if (layer instanceof L.CircleMarker) {
                        layer.setStyle({ fillColor: color });
                    } else {
                        layer.setStyle({ fillColor: color });
                    }
                });
            } else if (layerInfo.type === 'geojson') {
                // Update geojson layer colors
                const maxValue = layerInfo.maxValue;

                layerInfo.layer.eachLayer((layer) => {
                    if (layer.feature) {
                        const p = layer.feature.properties;
                        let val = 0;
                        if (p.GDP) val = parseFloat(p.GDP);
                        else if (p['GDP per capita, PPP (constant 2021 international $)']) val = parseFloat(p['GDP per capita, PPP (constant 2021 international $)']);
                        else if (p.Value) val = parseFloat(p.Value);
                        else if (p.OBS_VALUE) val = parseFloat(p.OBS_VALUE);

                        const color = getColor(val, maxValue, newScheme);
                        layer.setStyle({ fillColor: color });
                    }
                });
            }
        }

        console.log(`Color scheme for ${folder} changed to ${newScheme}`);
    });
});


// Opacity slider functionality
const opacitySlider = document.getElementById('opacitySlider');
const opacityValue = document.getElementById('opacityValue');

if (opacitySlider) {
    opacitySlider.addEventListener('input', function (e) {
        const val = parseFloat(e.target.value);
        if (opacityValue) opacityValue.textContent = `${Math.round(val * 100)}%`;

        // Update all active layers
        Object.values(activeLayers).forEach(layerInfo => {
            const layer = layerInfo.layer || layerInfo;
            if (layer.setOpacity) {
                layer.setOpacity(val);
            } else if (layer.eachLayer) {
                // For GeoJSON/choropleth layers
                layer.eachLayer(l => {
                    if (l.setStyle) l.setStyle({ fillOpacity: val });
                });
            }
        });
    });
}

// Basemap switcher logic is now consolidated at top of file
// Duplicate listener removed

// ============================
// Mobile Menu Logic
// ============================
document.addEventListener('DOMContentLoaded', () => {
    console.log('MENU SCRIPT OK');

    const menuBtn = document.getElementById('menuBtn');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');

    if (!menuBtn || !sidebar || !overlay) {
        console.error('Menu elements missing');
        return;
    }

    function openSidebar() {
        sidebar.classList.remove('-translate-x-full');
        overlay.classList.remove('hidden', 'opacity-0', 'pointer-events-none');
        overlay.classList.add('opacity-100');
        menuBtn.classList.add('sidebar-open');
    }

    function closeSidebar() {
        sidebar.classList.add('-translate-x-full');
        overlay.classList.add('opacity-0', 'pointer-events-none');
        setTimeout(() => overlay.classList.add('hidden'), 300);
        menuBtn.classList.remove('sidebar-open');
    }

    menuBtn.addEventListener('click', () => {
        sidebar.classList.contains('-translate-x-full')
            ? openSidebar()
            : closeSidebar();
    });

    overlay.addEventListener('click', closeSidebar);

    window.addEventListener('resize', () => {
        if (window.innerWidth >= 768) {
            sidebar.classList.remove('-translate-x-full');
            overlay.classList.add('hidden', 'opacity-0', 'pointer-events-none');
            menuBtn.classList.remove('sidebar-open');
        }
    });



    // Close sidebar when clicking on map (mobile UX) AND show weather data popup
    map.on('click', async (e) => {
        // Close sidebar on mobile (only close, don't toggle)
        if (window.innerWidth < 768 && !sidebar.classList.contains('-translate-x-full')) {
            closeSidebar();
        }


        // If weather layer is active, show weather data for clicked location
        const activeWeatherVars = Object.keys(weatherLayers);
        if (activeWeatherVars.length > 0) {
            const clickLat = e.latlng.lat;
            const clickLng = e.latlng.lng;

            // Get the active weather variable
            const variable = activeWeatherVars[0];
            const cachedData = weatherDataCache[variable];

            if (cachedData && cachedData.length > 0) {
                // Find the closest data point (using backend format: lat, lon, value)
                let closestPoint = null;
                let closestDist = Infinity;

                cachedData.forEach(point => {
                    const dist = Math.sqrt(
                        Math.pow(clickLat - point.lat, 2) +
                        Math.pow(clickLng - point.lon, 2)
                    );
                    if (dist < closestDist) {
                        closestDist = dist;
                        closestPoint = point;
                    }
                });

                // Show popup if the closest point is within reasonable range
                if (closestPoint && closestDist < 15) {
                    const scale = weatherColorScales[variable];
                    const value = closestPoint.value;

                    if (value !== null && value !== undefined) {
                        // Format time
                        const timeStr = weatherTimeLabels[currentWeatherHourIndex] || '';
                        let formattedTime = '';
                        if (timeStr) {
                            const date = new Date(timeStr);
                            formattedTime = date.toLocaleDateString('id-ID', {
                                day: 'numeric', month: 'short', year: 'numeric',
                                hour: '2-digit', minute: '2-digit'
                            });
                        }

                        const color = getWeatherColor(value, variable);

                        // Show popup
                        L.popup()
                            .setLatLng(e.latlng)
                            .setContent(`
                                    <div style="font-family: 'Outfit', system-ui, sans-serif; min-width: 140px;">
                                        <div style="font-size: 24px; font-weight: 700; color: ${color}; margin-bottom: 4px;">
                                            ${value.toFixed(1)}${scale.unit}
                                        </div>
                                        <div style="font-size: 12px; font-weight: 600; color: #d77b26;">
                                            ${scale.name}
                                        </div>
                                        <div style="font-size: 10px; color: #e68211; margin-top: 6px; padding-top: 6px; border-top: 1px solid #ff9500;">
                                            📍 ${closestPoint.lat.toFixed(2)}°, ${closestPoint.lon.toFixed(2)}°
                                        </div>
                                        ${formattedTime ? `<div style="font-size: 10px; color: #94a3b8;">🕐 ${formattedTime}</div>` : ''}
                                    </div>
                                `)
                            .openOn(map);
                    }
                }
            } else {
                // No cached data, fetch for clicked location using backend API
                try {
                    const url = `/api/weather-point?lat=${clickLat}&lon=${clickLng}`;
                    const response = await fetch(url);
                    if (response.ok) {
                        const data = await response.json();
                        if (data.success && data.current) {
                            const scale = weatherColorScales[variable];
                            const currentData = data.current[variable];
                            const value = currentData?.value;

                            if (value !== null && value !== undefined) {
                                const color = getWeatherColor(value, variable);

                                L.popup()
                                    .setLatLng(e.latlng)
                                    .setContent(`
                                            <div style="font-family: 'Outfit', system-ui, sans-serif; min-width: 140px;">
                                                <div style="font-size: 24px; font-weight: 700; color: ${color}; margin-bottom: 4px;">
                                                    ${value.toFixed(1)}${scale.unit}
                                                </div>
                                                <div style="font-size: 12px; font-weight: 600; color: #1e293b;">
                                                    ${scale.name}
                                                </div>
                                                <div style="font-size: 10px; color: #64748b; margin-top: 6px; padding-top: 6px; border-top: 1px solid #e2e8f0;">
                                                    📍 ${clickLat.toFixed(4)}°, ${clickLng.toFixed(4)}°
                                                </div>
                                            </div>
                                        `)
                                    .openOn(map);
                            }
                        }
                    }
                } catch (err) {
                    console.error('Error fetching weather for clicked location:', err);
                }
            }
        }
    });
});
// Handle window resize
window.addEventListener('resize', () => {
    if (window.innerWidth >= 768) {
        // Desktop: ensure sidebar is visible
        sidebar.classList.remove('-translate-x-full');
        overlay.classList.add('hidden', 'opacity-0', 'pointer-events-none');
    }
});

// ============================
// Dynamic Layer Refresh
// ============================

let currentLayerCount = document.querySelectorAll('.layer-toggle').length;

async function refreshLayers() {
    const refreshBtn = document.getElementById('refreshLayersBtn');
    const layerControls = document.getElementById('layersList');

    // Animate button
    refreshBtn.querySelector('svg').classList.add('animate-spin');

    try {
        const response = await fetch('/api/layers');
        const data = await response.json();

        if (data.success && data.layers) {
            // Rebuild layer list
            if (data.layers.length === 0) {
                layerControls.innerHTML = `
                            <div class="text-center py-8 px-4">
                                <svg class="w-12 h-12 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"></path>
                                </svg>
                                <p class="text-sm text-gray-500">Belum ada layer</p>
                                <p class="text-xs text-gray-400 mt-1">Upload GeoTIFF untuk memulai</p>
                            </div>`;
            } else {
                layerControls.innerHTML = data.layers.map(layer => `
                            <div class="layer-item flex items-center justify-between p-3 bg-gray-50 hover:bg-gray-100 rounded-lg transition-colors group">
                                <div class="flex-1 min-w-0 flex items-center gap-2">
                                    ${layer.layer_type === 'geojson' ? '<span class="text-sm" title="Point layer">📍</span>' : '<span class="text-sm" title="Tile layer">🗺️</span>'}
                                    <div>
                                        <p class="text-sm font-medium text-gray-800 truncate">${layer.name}</p>
                                        ${layer.description ? `<p class="text-xs text-gray-500 truncate">${layer.description}</p>` : ''}
                                    </div>
                                </div>
                                <label class="relative inline-flex items-center cursor-pointer ml-3 flex-shrink-0">
                                    <input type="checkbox" class="sr-only peer layer-toggle" data-folder="${layer.folder_path}" data-type="${layer.layer_type || 'tiles'}">
                                    <div class="toggle-switch w-10 h-5 bg-gray-300 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-5 peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 peer-checked:bg-blue-600"></div>
                                </label>
                            </div>
                        `).join('');

                // Re-attach event listeners
                attachLayerToggleListeners();
            }

            currentLayerCount = data.layers.length;
            console.log(`Layers refreshed: ${data.layers.length} layers`);
        }
    } catch (err) {
        console.error('Error refreshing layers:', err);
    }

    refreshBtn.querySelector('svg').classList.remove('animate-spin');
}

function attachLayerToggleListeners() {
    document.querySelectorAll('.layer-toggle').forEach(toggle => {
        toggle.addEventListener('change', async function () {
            const folder = this.dataset.folder;
            const layerType = this.dataset.type || 'tiles';
            const opacity = parseFloat(document.getElementById('opacitySlider').value);

            if (this.checked) {
                if (layerType === 'geojson') {
                    try {
                        // Use proxy API to bypass CORS
                        const response = await fetch(`/api/layer-data/${folder}`);
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        const geojsonData = await response.json();

                        const layer = L.geoJSON(geojsonData, {
                            pointToLayer: (feature, latlng) => {
                                return L.circleMarker(latlng, {
                                    radius: 8,
                                    fillColor: '#3b82f6',
                                    color: '#1e40af',
                                    weight: 2,
                                    opacity: 1,
                                    fillOpacity: opacity
                                });
                            },
                            onEachFeature: (feature, layer) => {
                                if (feature.properties) {
                                    let popupContent = '<div class="text-country">';
                                    if (feature.properties._popup) {
                                        popupContent += `<strong>${feature.properties._popup}</strong><hr class="my-1">`;
                                    }
                                    for (const [key, value] of Object.entries(feature.properties)) {
                                        if (key !== '_popup' && value) {
                                            popupContent += `<b>${key}:</b> ${value}<br>`;
                                        }
                                    }
                                    popupContent += '</div>';
                                    layer.bindPopup(popupContent);
                                }
                            }
                        }).addTo(map);

                        activeLayers[folder] = layer;

                        if (geojsonData.features.length > 0) {
                            map.fitBounds(layer.getBounds(), { padding: [50, 50] });
                        }
                    } catch (err) {
                        console.error('Error loading GeoJSON:', err);
                        this.checked = false;
                    }
                } else {
                    // Tile layer from R2 Storage
                    // Upscale tiles when zooming beyond available zoom levels
                    const layer = L.tileLayer(`${storageBaseUrl}/${folder}/{z}/{x}/{y}.png`, {
                        tms: false,
                        opacity: opacity,
                        maxZoom: 18,
                        minZoom: 0,
                        maxNativeZoom: 12,  // Tiles generated up to zoom 12, upscale beyond
                        errorTileUrl: ''
                    }).addTo(map);

                    console.log(`Added tile layer (refreshed): ${folder}`);
                    activeLayers[folder] = layer;
                }
            } else {
                if (activeLayers[folder]) {
                    map.removeLayer(activeLayers[folder]);
                    delete activeLayers[folder];
                }
            }
        });
    });
}

// Refresh button click
document.getElementById('refreshLayersBtn').addEventListener('click', refreshLayers);

// Auto-check for new layers every 30 seconds
setInterval(async () => {
    try {
        const response = await fetch('/api/layers');
        const data = await response.json();
        if (data.success && data.layers.length !== currentLayerCount) {
            // New layers available - show indicator
            document.getElementById('refreshLayersBtn').classList.add('text-blue-500', 'animate-pulse');
        }
    } catch (e) { }
}, 30000);

// ============================
// Map Event Logging (Development)
// ============================

map.on('moveend', function () {
    const center = map.getCenter();
    const zoom = map.getZoom();
    console.log(`Map View: [${center.lat.toFixed(4)}, ${center.lng.toFixed(4)}] @ Zoom ${zoom}`);
});

// (Weather variables weatherLayers, weatherMarkerLayers, weatherColorScales, and getWeatherColor 
// are declared at top of script for inline handler compatibility)

function buildGradient(variable) {
    const scale = weatherColorScales[variable] || weatherColorScales.temperature_2m;
    const gradient = {};
    scale.colors.forEach((color, i) => {
        gradient[i / (scale.colors.length - 1)] = color;
    });
    return gradient;
}

// Global handler for weather toggle (can be called from inline onchange)
async function handleWeatherToggle(checkbox) {
    const variable = checkbox.dataset.variable;
    console.log(`handleWeatherToggle called: ${variable}, checked: ${checkbox.checked}`);

    const card = checkbox.closest('.weather-layer-card');
    const hourControl = card.querySelector('.weather-hour-control');

    if (checkbox.checked) {
        try {
            card.classList.add('expanded');
            hourControl.classList.remove('hidden');

            console.log(`Activating weather layer: ${variable}`);

            // Zoom out to global view
            if (Object.keys(weatherLayers).length === 0) {
                map.flyTo([20, 0], 2, { duration: 1 });
            }

            const hourSlider = card.querySelector('.weather-hour-slider');

            // Default to current hour (important for UV index which is 0 at night)
            const currentHour = new Date().getHours();
            let hour = hourSlider ? parseInt(hourSlider.value) : currentHour;

            // If slider is at 0 (default), set it to current hour
            if (hourSlider && parseInt(hourSlider.value) === 0) {
                hourSlider.value = currentHour;
                hour = currentHour;
                // Update label
                const label = card.querySelector('.weather-hour-label');
                if (label) label.textContent = `+${currentHour}h`;
            }

            console.log(`Fetching weather for hour=${hour} (current hour: ${currentHour})`);

            await fetchAndRenderWeather(variable, hour);
            console.log('fetchAndRenderWeather completed');
        } catch (err) {
            console.error('ERROR in weather activation:', err);
            console.error('Stack:', err.stack);
        }
    } else {
        console.log(`Deactivating weather layer: ${variable}`);
        card.classList.remove('expanded');
        hourControl.classList.add('hidden');
        removeWeatherLayer(variable);
        hideWeatherTimeControl();
    }
}

// Fetch and render weather data - OPTIMIZED CHOROPLETH
var activeWeatherVariable = null;

async function fetchAndRenderWeather(variable, hourIndex = 0) {
    console.log(`>>> fetchAndRenderWeather OPTIMIZED: ${variable}, hour ${hourIndex}`);
    activeWeatherVariable = variable;
    const startTime = performance.now();

    try {
        // 1. Fetch weather data from backend (with caching on backend)
        const weatherUrl = `/api/weather-data?variable=${variable}&hour=${hourIndex}&resolution=15`;
        const weatherResponse = await fetch(weatherUrl);
        if (!weatherResponse.ok) {
            console.error(`Weather API error: ${weatherResponse.status}`);
            return;
        }
        const weatherResult = await weatherResponse.json();
        console.log(`Weather data: ${weatherResult.point_count} points (${(performance.now() - startTime).toFixed(0)}ms)`);

        if (!weatherResult.success || !weatherResult.data) {
            console.error('Weather data fetch failed:', weatherResult.error);
            return;
        }

        // Store time labels for display
        if (weatherResult.times && weatherResult.times.length > 0) {
            weatherTimeLabels = weatherResult.times;
            updateWeatherTimeDisplay(hourIndex);
        }

        // 2. Fetch/use cached countries GeoJSON
        if (!countriesGeoJSONCache) {
            console.log(`Fetching countries GeoJSON (first time)...`);
            const countriesResponse = await fetch('/api/countries-geojson');
            if (!countriesResponse.ok) {
                console.error(`Countries GeoJSON error: ${countriesResponse.status}`);
                return;
            }
            countriesGeoJSONCache = await countriesResponse.json();

            // Pre-calculate centroids for all countries (once!)
            countriesGeoJSONCache.features.forEach((feature, idx) => {
                const id = feature.properties.name || feature.properties.NAME || `country_${idx}`;
                try {
                    const tempLayer = L.geoJSON(feature);
                    const bounds = tempLayer.getBounds();
                    countryCentroidsCache[id] = bounds.getCenter();
                } catch (e) {
                    countryCentroidsCache[id] = { lat: 0, lng: 0 };
                }
            });
            console.log(`Countries cached: ${countriesGeoJSONCache.features.length} (centroids pre-calculated)`);
        }

        const scale = weatherColorScales[variable] || weatherColorScales.temperature_2m;

        // 3. Pre-calculate weather values for ALL countries (O(countries * weather_points) -> do ONCE, not per-feature)
        const countryWeatherValues = {};
        countriesGeoJSONCache.features.forEach((feature, idx) => {
            const id = feature.properties.name || feature.properties.NAME || `country_${idx}`;
            const centroid = countryCentroidsCache[id];

            // Find closest weather value
            let closestDist = Infinity;
            let closestValue = null;
            weatherResult.data.forEach(point => {
                const dist = Math.pow(centroid.lat - point.lat, 2) + Math.pow(centroid.lng - point.lon, 2);
                if (dist < closestDist) {
                    closestDist = dist;
                    closestValue = point.value;
                }
            });
            countryWeatherValues[id] = closestValue;
        });

        // Remove existing layers
        if (weatherLayers[variable]) {
            map.removeLayer(weatherLayers[variable]);
        }
        if (weatherMarkerLayers[variable]) {
            map.removeLayer(weatherMarkerLayers[variable]);
        }

        // 4. Create choropleth layer (fast - just lookup pre-calculated values)
        const choroplethLayer = L.geoJSON(countriesGeoJSONCache, {
            style: (feature) => {
                const id = feature.properties.name || feature.properties.NAME || 'Unknown';
                const value = countryWeatherValues[id];

                if (value === null || value === undefined) {
                    return { fillColor: '#ccc', weight: 0.5, opacity: 1, color: '#666', fillOpacity: 0.3 };
                }

                return {
                    fillColor: getWeatherColor(value, variable),
                    weight: 0.5,
                    opacity: 1,
                    color: '#fff',
                    fillOpacity: 0.75
                };
            },
            onEachFeature: (feature, layer) => {
                const countryName = feature.properties.name || feature.properties.NAME || 'Unknown';
                const value = countryWeatherValues[countryName];

                if (value !== null && value !== undefined) {
                    const color = getWeatherColor(value, variable);
                    layer.bindPopup(`
                                <div style="font-family: Outfit, sans-serif; text-align: center; min-width: 120px;">
                                    <div style="font-weight: 600; color: #ffffff; margin-bottom: 4px;">${countryName}</div>
                                    <div style="font-size: 24px; font-weight: 700; color: ${color};">${value.toFixed(1)}${scale.unit}</div>
                                    <div style="font-size: 11px; color: #fffcfba2;">${scale.name}</div>
                                </div>
                            `);
                }

                // Hover effect
                layer.on({
                    mouseover: (e) => e.target.setStyle({ weight: 2, color: '#333' }),
                    mouseout: (e) => choroplethLayer.resetStyle(e.target)
                });
            }
        });

        choroplethLayer.addTo(map);
        weatherLayers[variable] = choroplethLayer;

        // Store data in cache
        weatherDataCache[variable] = weatherResult.data;
        currentWeatherHourIndex = hourIndex;

        console.log(`Weather choropleth rendered in ${(performance.now() - startTime).toFixed(0)}ms`);

        // Update legend
        updateWeatherLegend(variable);

        // Show weather time control
        showWeatherTimeControl(variable, hourIndex);

    } catch (err) {
        console.error(`Error fetching weather:`, err);
    }
}

// Update weather time display with actual datetime
function updateWeatherTimeDisplay(hourIndex) {
    const timeLabel = document.getElementById('weatherTimeLabel');
    if (timeLabel && weatherTimeLabels[hourIndex]) {
        const date = new Date(weatherTimeLabels[hourIndex]);
        const options = {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        };
        timeLabel.textContent = date.toLocaleDateString('id-ID', options);
    }
}

// Update weather legend
function updateWeatherLegend(variable) {
    const scale = weatherColorScales[variable];
    if (!scale) return;

    const legendContainer = document.getElementById('legendContainer');
    const legendTitle = document.getElementById('legendTitle');
    const legendMin = document.getElementById('legendMin');
    const legendMax = document.getElementById('legendMax');
    const legendMed = document.getElementById('legendMed');
    const legendGradient = document.getElementById('legendGradient');

    legendTitle.textContent = `${scale.name} (${scale.unit})`;
    legendMin.textContent = scale.min.toString();
    legendMax.textContent = scale.max.toString();
    legendMed.textContent = ((scale.min + scale.max) / 2).toFixed(0);
    legendGradient.style.background = `linear-gradient(to right, ${scale.colors.join(', ')})`;

    legendContainer.classList.add('active');
}

// Show weather time control floating at bottom of map
function showWeatherTimeControl(variable, currentHour) {
    let control = document.getElementById('weatherTimeControl');
    if (!control) {
        control = document.createElement('div');
        control.id = 'weatherTimeControl';
        control.innerHTML = `
                    <div style="background: rgba(255,255,255,0.95); backdrop-filter: blur(10px); padding: 16px 24px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.15); display: flex; align-items: center; gap: 16px; font-family: system-ui, sans-serif;">
                        <button id="weatherPlayBtn" style="width: 36px; height: 36px; border-radius: 50%; border: none; background: linear-gradient(135deg, #667eea, #764ba2); color: white; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 14px;">▶</button>
                        <div style="flex: 1; min-width: 200px;">
                            <div id="weatherTimeLabel" style="font-size: 18px; font-weight: 600; color: #1a1a2e; margin-bottom: 4px;">Loading...</div>
                            <input type="range" id="weatherTimeSlider" min="0" max="71" value="${currentHour}" style="width: 100%; accent-color: #667eea;">
                        </div>
                    </div>
                `;
        control.style.cssText = 'position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%); z-index: 1000;';
        document.getElementById('map').appendChild(control);

        // Event listeners
        const slider = document.getElementById('weatherTimeSlider');

        // ambil jam sekarang (0–23)
        const nowHour = new Date().getHours();

        // set default value slider
        slider.value = nowHour;

        // update tampilan jam
        updateWeatherTimeDisplay(nowHour);

        // render cuaca awal kalau ada variabel aktif
        if (activeWeatherVariable) {
            fetchAndRenderWeather(activeWeatherVariable, nowHour);
        }

        // listener tetap
        slider.addEventListener('input', async function () {
            const hour = parseInt(this.value);
            updateWeatherTimeDisplay(hour);
            if (activeWeatherVariable) {
                await fetchAndRenderWeather(activeWeatherVariable, hour);
            }
        });

        // Play button
        let isPlaying = false;
        let playInterval = null;
        document.getElementById('weatherPlayBtn').addEventListener('click', function () {
            isPlaying = !isPlaying;
            this.textContent = isPlaying ? '⏸' : '▶';

            if (isPlaying) {
                playInterval = setInterval(async () => {
                    const slider = document.getElementById('weatherTimeSlider');
                    let hour = parseInt(slider.value) + 1;
                    if (hour > 71) hour = 0;
                    slider.value = hour;
                    updateWeatherTimeDisplay(hour);
                    if (activeWeatherVariable) {
                        await fetchAndRenderWeather(activeWeatherVariable, hour);
                    }
                }, 1500);
            } else {
                clearInterval(playInterval);
            }
        });
    }

    control.style.display = 'block';
    updateWeatherTimeDisplay(currentHour);
}

function hideWeatherTimeControl() {
    const control = document.getElementById('weatherTimeControl');
    if (control) control.style.display = 'none';
}

function renderWeatherForVariable(variable, data) {
    console.log(`renderWeatherForVariable called: ${variable}`);
    console.log(`Data points: ${data.data ? data.data.length : 0}`);

    // Remove existing layers for this variable
    if (weatherLayers[variable]) {
        map.removeLayer(weatherLayers[variable]);
    }
    if (weatherMarkerLayers[variable]) {
        map.removeLayer(weatherMarkerLayers[variable]);
    }

    if (!data.data || data.data.length === 0) {
        console.log('No data to render!');
        return;
    }

    const scale = weatherColorScales[variable] || weatherColorScales.temperature_2m;
    console.log(`Scale: min=${scale.min}, max=${scale.max}`);

    // Create circle markers
    const markers = L.layerGroup();
    let markerCount = 0;

    data.data.forEach(point => {
        const color = getWeatherColor(point.value, variable);

        const circle = L.circleMarker([point.lat, point.lon], {
            radius: 35,
            fillColor: color,
            color: 'rgba(255,255,255,0.6)',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.8
        });

        circle.bindPopup(`
                    <div class="text-sm font-medium">
                        <div class="text-lg font-bold text-gray-800">${point.value.toFixed(1)} ${data.unit}</div>
                        <div class="text-gray-500">${scale.name}</div>
                        <div class="text-xs text-gray-400 mt-1">${point.lat.toFixed(2)}°, ${point.lon.toFixed(2)}°</div>
                    </div>
                `);

        markers.addLayer(circle);
        markerCount++;
    });

    console.log(`Created ${markerCount} circle markers`);
    weatherMarkerLayers[variable] = markers;
    markers.addTo(map);
    console.log('Circle markers added to map');

    // Create heatmap layer
    const heatPoints = data.data.map(point => {
        const intensity = (point.value - scale.min) / (scale.max - scale.min);
        return [point.lat, point.lon, Math.max(0.1, Math.min(1, intensity))];
    });

    console.log(`Heat points: ${heatPoints.length}, checking if L.heatLayer exists: ${typeof L.heatLayer}`);

    if (typeof L.heatLayer === 'function') {
        weatherLayers[variable] = L.heatLayer(heatPoints, {
            radius: 45,
            blur: 35,
            maxZoom: 10,
            max: 1.0,
            gradient: buildGradient(variable)
        }).addTo(map);
        console.log('Heatmap layer added to map');
    } else {
        console.error('L.heatLayer is not available! Make sure leaflet-heat is loaded.');
    }

    markers.bringToFront();
    console.log('Render complete');
}

function updateWeatherLegendForVariable(variable, data) {
    const legendContainer = document.getElementById('legendContainer');
    const legendTitle = document.getElementById('legendTitle');
    const legendMin = document.getElementById('legendMin');
    const legendMax = document.getElementById('legendMax');
    const legendMed = document.getElementById('legendMed');
    const legendGradient = document.getElementById('legendGradient');

    const scale = weatherColorScales[variable];

    legendTitle.textContent = `${scale.name} (${scale.unit})`;
    legendMin.textContent = scale.min.toString();
    legendMax.textContent = scale.max.toString();
    legendMed.textContent = ((scale.min + scale.max) / 2).toFixed(0);
    legendGradient.style.background = `linear-gradient(to right, ${scale.colors.join(', ')})`;

    legendContainer.classList.add('active');
}

function removeWeatherLayer(variable) {
    if (weatherLayers[variable]) {
        map.removeLayer(weatherLayers[variable]);
        delete weatherLayers[variable];
    }
    if (weatherMarkerLayers[variable]) {
        map.removeLayer(weatherMarkerLayers[variable]);
        delete weatherMarkerLayers[variable];
    }

    // Hide legend if no weather layers active
    const hasActiveWeather = Object.keys(weatherLayers).length > 0;
    const hasOtherChoropleth = Object.values(activeLayers).some(l => l.type === 'choropleth');
    if (!hasActiveWeather && !hasOtherChoropleth) {
        document.getElementById('legendContainer').classList.remove('active');
    }
}

// Attach event listeners to all weather toggles
console.log('Setting up weather toggles...');
const weatherToggles = document.querySelectorAll('.weather-toggle');
console.log(`Found ${weatherToggles.length} weather toggles`);

weatherToggles.forEach(toggle => {
    console.log(`Attaching listener to: ${toggle.dataset.variable}`);
    toggle.addEventListener('change', async function () {
        const variable = this.dataset.variable;
        console.log(`Weather toggle changed: ${variable}, checked: ${this.checked}`);

        const card = this.closest('.weather-layer-card');
        const hourControl = card.querySelector('.weather-hour-control');

        if (this.checked) {
            card.classList.add('expanded');
            hourControl.classList.remove('hidden');

            console.log(`Activating weather layer: ${variable}`);

            // Zoom out to see global data on first weather layer activation
            if (Object.keys(weatherLayers).length === 0) {
                map.flyTo([20, 0], 2, { duration: 1 });
            }

            // Get current hour value
            const hourSlider = card.querySelector('.weather-hour-slider');
            const hour = parseInt(hourSlider.value);

            await fetchAndRenderWeather(variable, hour);
        } else {
            console.log(`Deactivating weather layer: ${variable}`);
            card.classList.remove('expanded');
            hourControl.classList.add('hidden');
            removeWeatherLayer(variable);
        }
    });
});

// Attach hour slider handlers
document.querySelectorAll('.weather-hour-slider').forEach(slider => {
    let sliderTimeout = null;

    slider.addEventListener('input', function () {
        const card = this.closest('.weather-layer-card');
        const variable = card.dataset.variable;
        const hourLabel = card.querySelector('.weather-hour-label');
        const hour = parseInt(this.value);

        hourLabel.textContent = `+${hour}h`;

        // Debounce API calls
        clearTimeout(sliderTimeout);
        sliderTimeout = setTimeout(async () => {
            const toggle = card.querySelector('.weather-toggle');
            if (toggle.checked) {
                await fetchAndRenderWeather(variable, hour);
            }
        }, 400);
    });
});

// ============================
// Correlation Analysis Feature
// ============================



/**
 * Initialize correlation feature on page load
 */
async function initCorrelationFeature() {
    console.log('initCorrelationFeature: Starting...');
    try {
        // Fetch all layers from API
        const response = await fetch('/api/layers');
        if (!response.ok) {
            console.error('initCorrelationFeature: API response not OK');
            return;
        }

        const data = await response.json();
        if (!data.success) {
            console.error('initCorrelationFeature: API returned success=false');
            return;
        }

        // Filter only choropleth layers
        correlationState.layers = data.layers.filter(l => l.layer_type === 'choropleth');
        console.log(`initCorrelationFeature: Found ${correlationState.layers.length} choropleth layers. Prefetching metadata...`);

        // Populate Layer 1 dropdown
        const select1 = document.getElementById('correlationLayer1');
        const select2 = document.getElementById('correlationLayer2');
        const analyzeBtn = document.getElementById('correlationAnalyzeBtn');

        if (select1) {
            // Preservation logic: Check if browser restored a value
            const preservedValue = select1.value;
            console.log('initCorrelationFeature: Preserved value detected:', preservedValue);

            select1.innerHTML = '<option value="">-- Pilih Layer --</option>';
            correlationState.layers.forEach(layer => {
                const option = document.createElement('option');
                option.value = layer.folder_path;
                option.textContent = layer.name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

                // Re-select if matches preserved value
                if (preservedValue && layer.folder_path === preservedValue) {
                    option.selected = true;
                }
                select1.appendChild(option);
            });

            // ROBUST LISTENER ATTACHMENT (overrides any previous listeners)
            select1.onchange = async () => {
                console.log('Listener: Layer 1 changed to', select1.value);
                await updateCorrelationLayer2();
            };

            // Trigger update immediately if we restored a value
            if (select1.value) {
                console.log('initCorrelationFeature: Auto-triggering update for restored value...');
                // Use setTimeout to ensure DOM is ready
                setTimeout(() => updateCorrelationLayer2(), 50);
            }
        }

        // Attach other listeners robustly
        if (select2) select2.onchange = validateCorrelationSelection;
        if (analyzeBtn) analyzeBtn.onclick = runCorrelationAnalysis;

        // PREFETCH METADATA IN PARALLEL
        const promises = correlationState.layers.map(layer => getLayerType(layer.folder_path));
        await Promise.all(promises);

        console.log('initCorrelationFeature: All layer types loaded.');

        // Final consistency check
        if (select1 && select1.value) {
            updateCorrelationLayer2();
        }

    } catch (err) {
        console.error('Failed to init correlation:', err);
    }
}

/**
 * Get layer type (province or global) by checking choropleth metadata
 */
async function getLayerType(folder) {
    // Check cache first
    if (correlationState.layerMetadata[folder]) {
        return correlationState.layerMetadata[folder].type;
    }

    try {
        const response = await fetch(`/api/choropleth-data/${folder}`);
        if (!response.ok) return null;

        const data = await response.json();
        const isProvince = data.geojson_file === 'indonesia-provinces.geojson';

        // Cache result
        correlationState.layerMetadata[folder] = {
            type: isProvince ? 'province' : 'global',
            name: data.value_column || folder
        };

        return correlationState.layerMetadata[folder].type;
    } catch (err) {
        console.error('Failed to get layer type:', err);
        return null;
    }
}

async function updateCorrelationLayer2() {
    console.log('DEBUG: updateCorrelationLayer2 triggered (Strict Sync Mode)');
    const select1 = document.getElementById('correlationLayer1');
    const select2 = document.getElementById('correlationLayer2');
    const analyzeBtn = document.getElementById('correlationAnalyzeBtn');
    const warning = document.getElementById('correlationWarning');
    const warningText = document.getElementById('correlationWarningText');

    const folder1 = select1.value;
    correlationState.layer1 = folder1;
    correlationState.layer2 = null;

    // Reset states
    warning.classList.add('hidden');
    analyzeBtn.disabled = true;

    if (!folder1) {
        select2.innerHTML = '<option value="">-- Pilih Layer 1 terlebih dahulu --</option>';
        select2.disabled = true;
        return;
    }

    // 1. Resolve Layer 1 Type (Prioritize Cache)
    let type1 = 'global';
    if (correlationState.layerMetadata[folder1]) {
        type1 = correlationState.layerMetadata[folder1].type;
        console.log(`DEBUG: Layer 1 type (cache): ${type1}`);
    } else {
        // Fallback fetch if missing (should not happen if init completed)
        console.log('DEBUG: Layer 1 cache miss, fetching...');
        try {
            const t1 = await getLayerType(folder1);
            if (t1) type1 = t1;
        } catch (e) { console.error(e); }
    }

    // 2. Populate Layer 2 (Synchronous Loop)
    select2.disabled = false;
    select2.innerHTML = '<option value="">-- Pilih Layer --</option>';

    let compatibleCount = 0;
    const optionsFragment = document.createDocumentFragment();

    // Iterate all layers to populate options
    for (const layer of correlationState.layers) {
        if (layer.folder_path === folder1) continue; // Skip self

        const option = document.createElement('option');
        option.value = layer.folder_path;
        option.textContent = layer.name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

        // Resolve Layer 2 Type (Cache preferred)
        let type2 = 'global'; // Assume global if unknown to allow render
        if (correlationState.layerMetadata[layer.folder_path]) {
            type2 = correlationState.layerMetadata[layer.folder_path].type;
        } else {
            // If metadata is completely missing, we have to assume compatibility or fetch?
            // Since init prefetches all, strict filtering based on cache is safer UX than waiting.
            // If miss, we treat as 'global' (default)
        }

        // STRICT FILTER LOGIC:
        if (type1 !== type2) {
            option.disabled = true; // Disable incompatible
            option.textContent += ` (${type2 === 'province' ? 'Provinsi' : 'Global'}) - Beda Tipe`;
            option.style.color = '#ccc';
        } else {
            compatibleCount++; // Only count actual compatible ones
        }

        optionsFragment.appendChild(option);
    }

    select2.appendChild(optionsFragment);
    console.log(`DEBUG: Logged ${compatibleCount} compatible layers.`);

    if (compatibleCount === 0) {
        warning.classList.remove('hidden');
        if (warningText) warningText.textContent = `Tidak ada layer ${type1 === 'province' ? 'provinsi' : 'global'} lain yang tersedia.`;
    }
}

/**
 * Validate and enable/disable analyze button
 */
function validateCorrelationSelection() {
    const select1 = document.getElementById('correlationLayer1');
    const select2 = document.getElementById('correlationLayer2');
    const analyzeBtn = document.getElementById('correlationAnalyzeBtn');

    correlationState.layer2 = select2.value;

    const isValid = select1.value && select2.value && select1.value !== select2.value;
    analyzeBtn.disabled = !isValid;
}

/**
 * Run correlation analysis
 */
async function runCorrelationAnalysis() {
    const layer1 = correlationState.layer1;
    const layer2 = correlationState.layer2;

    if (!layer1 || !layer2) return;

    // Show loading state
    const loadingEl = document.getElementById('correlationLoading');
    const resultsEl = document.getElementById('correlationResults');
    const analyzeBtn = document.getElementById('correlationAnalyzeBtn');
    const btnText = document.getElementById('correlationBtnText');

    loadingEl.classList.remove('hidden');
    resultsEl.classList.add('hidden');
    analyzeBtn.disabled = true;
    btnText.textContent = 'Menganalisis...';

    try {
        // Get current year from slider if active
        const yearSlider = document.getElementById('yearSlider');
        const yearDisplay = document.getElementById('yearDisplay');
        const year = yearDisplay?.textContent || 'all';

        const response = await fetch(`/api/correlation?layer1=${layer1}&layer2=${layer2}&year=${year}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Gagal menghitung korelasi');
        }

        // Display results
        displayCorrelationResults(data);

    } catch (err) {
        console.error('Correlation error:', err);
        alert(`Error: ${err.message}`);
    } finally {
        loadingEl.classList.add('hidden');
        analyzeBtn.disabled = false;
        btnText.textContent = 'Analisis Korelasi';
    }
}

/**
 * Display correlation results in the UI
 */
function displayCorrelationResults(data) {
    const resultsEl = document.getElementById('correlationResults');
    const scoreBadge = document.getElementById('correlationScoreBadge');
    const strengthBadge = document.getElementById('correlationStrengthBadge');
    const directionBadge = document.getElementById('correlationDirectionBadge');
    const insightText = document.getElementById('correlationInsightText');
    const matchedRegions = document.getElementById('correlationMatchedRegions');
    const yearEl = document.getElementById('correlationYear');

    // Score
    const score = data.score || 0;
    scoreBadge.textContent = `r = ${score.toFixed(2)}`;

    // Remove old classes
    scoreBadge.className = 'correlation-score-badge px-3 py-1 rounded-full text-xs font-bold';

    // Add color class based on score
    const absScore = Math.abs(score);
    if (absScore > 0.7) {
        scoreBadge.classList.add(score > 0 ? 'positive-strong' : 'negative-strong');
    } else if (absScore > 0.3) {
        scoreBadge.classList.add(score > 0 ? 'positive-moderate' : 'negative-moderate');
    } else {
        scoreBadge.classList.add('weak');
    }

    // Strength
    const strength = data.strength || 'lemah';
    strengthBadge.textContent = strength.charAt(0).toUpperCase() + strength.slice(1);
    strengthBadge.className = 'inline-block px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider';

    if (strength === 'sangat kuat') {
        strengthBadge.classList.add('strength-sangat-kuat');
    } else if (strength === 'cukup kuat') {
        strengthBadge.classList.add('strength-cukup-kuat');
    } else if (strength === 'moderat') {
        strengthBadge.classList.add('strength-moderat');
    } else {
        strengthBadge.classList.add('strength-lemah');
    }

    // Direction
    const direction = data.direction || 'positif';
    directionBadge.textContent = direction.charAt(0).toUpperCase() + direction.slice(1);
    directionBadge.className = 'inline-block ml-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider';
    directionBadge.classList.add(direction === 'positif' ? 'direction-positif' : 'direction-negatif');

    // Insight text (enhanced markdown parsing with proper spacing)
    const text = data.text || 'No insight available.';
    let html = text
        // Headers: bold text followed by colon becomes styled header
        .replace(/\*\*(.*?):\*\*/g, '<div class="font-bold text-gray-800 dark:text-gray-200 mt-4 mb-2">$1</div>')
        // Bold text
        .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-700 dark:text-gray-300">$1</strong>')
        // Bullets: styled list items
        .replace(/• (.*?)(?=\n|$)/g, '<div class="flex items-start gap-2 ml-2 my-1"><span class="text-indigo-500 mt-0.5">•</span><span class="text-gray-600 dark:text-gray-400">$1</span></div>')
        // Double newlines: section breaks
        .replace(/\n\n/g, '<div class="my-3"></div>')
        // Single newlines
        .replace(/\n/g, '');
    insightText.innerHTML = '<div class="text-sm leading-relaxed">' + html + '</div>';

    // Statistics
    matchedRegions.textContent = data.matched_regions || 0;
    yearEl.textContent = data.year || 'All';

    // Scatter Chart (Plotly) - Interactive with Regressions
    const chartContainer = document.getElementById('correlationChart');
    const regressionControls = document.getElementById('regressionControls');
    const equationEl = document.getElementById('regressionEquation');

    if (data.plotly_data && chartContainer) {
        chartContainer.classList.remove('hidden');
        document.getElementById('chartZoomControls').classList.remove('hidden');

        // Show controls if regressions exist
        if (data.regressions && Object.keys(data.regressions).length > 0) {
            regressionControls.classList.remove('hidden');
            if (equationEl) equationEl.classList.remove('hidden');
        } else {
            regressionControls.classList.add('hidden');
        }

        // Store data for redraws within the existing state object
        correlationState.currentData = data;

        // Initial render with 'linear'
        renderInteractiveChart('linear');

        // Bind button events for regression toggles
        document.querySelectorAll('.regression-btn').forEach(btn => {
            // Remove old listeners to prevent duplicates (cloning trick)
            const newBtn = btn.cloneNode(true);
            btn.parentNode.replaceChild(newBtn, btn);

            newBtn.addEventListener('click', (e) => {
                const model = e.target.dataset.model;

                // Update active state
                document.querySelectorAll('.regression-btn').forEach(b => b.classList.remove('active', 'bg-indigo-50', 'text-indigo-700', 'border-indigo-200'));
                e.target.classList.add('active', 'bg-indigo-50', 'text-indigo-700', 'border-indigo-200');

                // Redraw
                renderInteractiveChart(model);
            });
        });

        // Zoom Controls Logic
        const zoomControls = document.getElementById('chartZoomControls');
        if (zoomControls) {
            zoomControls.classList.remove('hidden');

            // Zoom In button
            const zoomInBtn = document.getElementById('zoomInBtn');
            if (zoomInBtn) zoomInBtn.onclick = () => {
                try {
                    const xRange = chartContainer._fullLayout.xaxis.range;
                    const yRange = chartContainer._fullLayout.yaxis.range;
                    const xCenter = (xRange[0] + xRange[1]) / 2;
                    const yCenter = (yRange[0] + yRange[1]) / 2;
                    const xSpan = (xRange[1] - xRange[0]) * 0.4;
                    const ySpan = (yRange[1] - yRange[0]) * 0.4;
                    Plotly.relayout(chartContainer, {
                        'xaxis.range': [xCenter - xSpan, xCenter + xSpan],
                        'yaxis.range': [yCenter - ySpan, yCenter + ySpan]
                    });
                } catch (e) { console.error(e); }
            };

            // Zoom Out button
            const zoomOutBtn = document.getElementById('zoomOutBtn');
            if (zoomOutBtn) zoomOutBtn.onclick = () => {
                try {
                    const xRange = chartContainer._fullLayout.xaxis.range;
                    const yRange = chartContainer._fullLayout.yaxis.range;
                    const xCenter = (xRange[0] + xRange[1]) / 2;
                    const yCenter = (yRange[0] + yRange[1]) / 2;
                    const xSpan = (xRange[1] - xRange[0]) * 1.25;
                    const ySpan = (yRange[1] - yRange[0]) * 1.25;
                    Plotly.relayout(chartContainer, {
                        'xaxis.range': [xCenter - xSpan, xCenter + xSpan],
                        'yaxis.range': [yCenter - ySpan, yCenter + ySpan]
                    });
                } catch (e) { console.error(e); }
            };

            // Reset Zoom button
            const resetBtn = document.getElementById('resetZoomBtn');
            if (resetBtn) resetBtn.onclick = () => {
                Plotly.relayout(chartContainer, {
                    'xaxis.autorange': true,
                    'yaxis.autorange': true
                });
            };
        }

    } else if (chartContainer) {
        chartContainer.classList.add('hidden');
        if (equationEl) equationEl.classList.add('hidden');
    }

    // Show results
    resultsEl.classList.remove('hidden');
    // Scroll to results
    resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Render interactive chart based on selected regression model
 */
function renderInteractiveChart(modelType) {
    const data = correlationState.currentData;
    if (!data || !data.plotly_data) return;

    const plotData = data.plotly_data;
    const chartContainer = document.getElementById('correlationChart');
    const equationEl = document.getElementById('regressionEquation');

    // 1. Scatter Trace (Always present)
    const traces = [{
        x: plotData.x,
        y: plotData.y,
        mode: 'markers',
        type: 'scatter',
        name: 'Data',
        marker: {
            size: 10,
            color: '#6366f1',
            line: { color: 'white', width: 1 },
            opacity: 0.7
        }
    }];

    // 2. Add Regression Trace if available
    let equationText = "Model not suitable for this data";

    if (data.regressions && data.regressions[modelType]) {
        const reg = data.regressions[modelType];
        traces.push({
            x: reg.x,
            y: reg.y,
            mode: 'lines',
            type: 'scatter',
            name: `${modelType.charAt(0).toUpperCase() + modelType.slice(1)} Fit`,
            line: { color: '#ef4444', width: 3 }
        });
        equationText = reg.equation;
    } else {
        // equationText remains default
    }

    // Update equation display
    if (equationEl) equationEl.textContent = equationText;

    // Layout
    const layout = {
        title: {
            text: `${plotData.layer1_name} vs ${plotData.layer2_name}`,
            font: { size: 12, family: 'Plus Jakarta Sans, sans-serif', color: '#64748b' }
        },
        xaxis: {
            title: plotData.layer1_name,
            showgrid: true,
            gridcolor: '#e2e8f0',
            zerolinecolor: '#e2e8f0',
            titlefont: { size: 11, family: 'Plus Jakarta Sans, sans-serif' },
            tickfont: { size: 10 }
        },
        yaxis: {
            title: plotData.layer2_name,
            showgrid: true,
            gridcolor: '#e2e8f0',
            zerolinecolor: '#e2e8f0',
            titlefont: { size: 11, family: 'Plus Jakarta Sans, sans-serif' },
            tickfont: { size: 10 }
        },
        margin: { l: 50, r: 20, t: 40, b: 40 },
        height: 300,
        paper_bgcolor: 'rgba(255,255,255,0)',
        plot_bgcolor: 'rgba(255,255,255,0)',
        font: { family: 'Plus Jakarta Sans, sans-serif', color: '#334155' },
        showlegend: false,
        dragmode: 'pan',
        hovermode: 'closest'
    };

    const config = {
        scrollZoom: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
        displaylogo: false,
        responsive: true
    };

    Plotly.newPlot(chartContainer, traces, layout, config);
}

// Event Listeners for Correlation & Dark Mode
document.addEventListener('DOMContentLoaded', () => {
    // Initialize Dark Mode
    initDarkMode();

    // Initialize Correlation
    initCorrelationFeature();

    // Layer 1 change
    const select1 = document.getElementById('correlationLayer1');
    if (select1) {
        select1.addEventListener('change', updateCorrelationLayer2);
    }

    // Layer 2 change
    const select2 = document.getElementById('correlationLayer2');
    if (select2) {
        select2.addEventListener('change', validateCorrelationSelection);
    }

    // Analyze button
    const analyzeBtn = document.getElementById('correlationAnalyzeBtn');
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', runCorrelationAnalysis);
    }
});

// Dark Mode Logic
function initDarkMode() {
    console.log('=== DARK MODE INIT STARTED ===');
    try {
        const toggleBtn = document.getElementById('darkModeToggle');
        const html = document.documentElement;

        // Safely check saved preference
        let isDark = false;
        try {
            const saved = localStorage.getItem('theme');
            const sys = window.matchMedia('(prefers-color-scheme: dark)').matches;
            isDark = saved === 'dark' || (!saved && sys);
        } catch (e) {
            console.warn('LocalStorage access failed:', e);
        }

        // Apply initial state
        if (isDark) html.classList.add('dark');
        else html.classList.remove('dark');

        if (toggleBtn) {
            // Handler function
            const toggleDarkMode = (e) => {
                e.preventDefault();
                e.stopPropagation();

                if (html.classList.contains('dark')) {
                    html.classList.remove('dark');
                    try { localStorage.setItem('theme', 'light'); } catch (e) { }
                    console.log('Switched to light mode');
                } else {
                    html.classList.add('dark');
                    try { localStorage.setItem('theme', 'dark'); } catch (e) { }
                    console.log('Switched to dark mode');
                }
            };

            // Use both onclick and addEventListener for robustness
            toggleBtn.onclick = toggleDarkMode;
            toggleBtn.addEventListener('click', toggleDarkMode);
            console.log('Dark Mode toggle instantiated.');
        } else {
            console.error('Dark Mode toggle button not found in DOM.');
        }
    } catch (err) {
        console.error('Critical error in initDarkMode:', err);
    }
}

// Fullscreen Chart Handler - Global Function
function openFullscreenChart() {
    console.log('openFullscreenChart called');
    const layer1 = document.getElementById('correlationLayer1')?.value;
    const layer2 = document.getElementById('correlationLayer2')?.value;
    const yearElem = document.getElementById('correlationYear');
    const year = yearElem ? yearElem.textContent.trim() : '2024';

    console.log('Fullscreen params:', { layer1, layer2, year });

    if (!layer1 || !layer2) {
        alert('Please perform a correlation analysis first.');
        return;
    }

    const url = `/chart-fullscreen?layer1=${encodeURIComponent(layer1)}&layer2=${encodeURIComponent(layer2)}&year=${encodeURIComponent(year)}`;
    console.log('Opening URL:', url);

    const newWindow = window.open(url, '_blank');
    if (!newWindow || newWindow.closed || typeof newWindow.closed == 'undefined') {
        alert('Popup blocked! Please allow popups for this site.');
    }
}

function initFullscreenHandler() {
    const btn = document.getElementById('viewFullscreenBtn');
    if (btn) {
        btn.addEventListener('click', openFullscreenChart);
        console.log('Fullscreen handler initialized');
    }
}
document.addEventListener('DOMContentLoaded', initFullscreenHandler);

// Chart.js 래퍼: 토큰 색상, 얇은 마크, 크로스헤어 툴팁
import { fmt } from './ui.js';

function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const crosshair = {
    id: 'crosshair',
    afterDatasetsDraw(chart) {
        const active = chart.tooltip && chart.tooltip.getActiveElements ? chart.tooltip.getActiveElements() : [];
        if (!active.length) return;
        const { ctx, chartArea } = chart;
        const x = active[0].element.x;
        ctx.save();
        ctx.strokeStyle = cssVar('--muted-2');
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, chartArea.top);
        ctx.lineTo(x, chartArea.bottom);
        ctx.stroke();
        ctx.restore();
    },
};

function baseOptions({ yFormatter = fmt.compact, tooltipTitle } = {}) {
    const muted = cssVar('--muted');
    const hairline = cssVar('--hairline');
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 250 },
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: cssVar('--surface'),
                titleColor: cssVar('--text'),
                bodyColor: cssVar('--text'),
                borderColor: cssVar('--border'),
                borderWidth: 1,
                padding: 10,
                displayColors: false,
                callbacks: {
                    title: (items) => (tooltipTitle ? tooltipTitle(items) : items[0].label),
                    label: (item) => `${item.dataset.label}: ${fmt.int(item.raw)}`,
                },
            },
        },
        scales: {
            x: {
                grid: { display: false },
                ticks: { color: muted, font: { size: 11 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
                border: { color: hairline },
            },
            y: {
                grid: { color: hairline, drawTicks: false },
                border: { display: false },
                ticks: { color: muted, font: { size: 11 }, callback: (v) => yFormatter(v), maxTicksLimit: 6 },
            },
        },
    };
}

export function hasChartJs() {
    return typeof window.Chart !== 'undefined';
}

export function lineChart(canvas, { labels, values, label, color = null, fill = true }) {
    if (!hasChartJs()) return null;
    const series = color || cssVar('--series-1');
    return new window.Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label,
                data: values,
                borderColor: series,
                backgroundColor: fill ? series + '1f' : 'transparent',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: series,
                pointHoverBorderColor: cssVar('--surface'),
                pointHoverBorderWidth: 2,
                fill,
                tension: 0.25,
                spanGaps: true,
            }],
        },
        options: baseOptions({}),
        plugins: [crosshair],
    });
}

export function barChart(canvas, { labels, values, label, color = null, signed = false }) {
    if (!hasChartJs()) return null;
    const series = color || cssVar('--series-1');
    const danger = cssVar('--danger');
    const colors = values.map(v => (signed && v < 0 ? danger : series));
    return new window.Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label,
                data: values,
                backgroundColor: colors,
                borderRadius: 4,
                borderSkipped: 'bottom',
                maxBarThickness: 24,
                categoryPercentage: 0.8,
                barPercentage: 0.9,
            }],
        },
        options: baseOptions({}),
        plugins: [],
    });
}

export function destroyChart(chart) {
    if (chart && typeof chart.destroy === 'function') chart.destroy();
}

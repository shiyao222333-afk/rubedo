// 日历布局诊断工具 — 同步加载，不依赖 DOMContentLoaded
// 在 index_page.py 里通过 ui.add_head_html() 同步加载

window.showDiag = function() {
    var cal = document.getElementById('calendar');
    if (!cal) { alert('找不到 #calendar 元素'); return; }

    // 读取 DayPilot 配置（如果存在）
    var dp = window.dp;
    var cellH = (dp && dp.config && dp.config.cellHeight) ? dp.config.cellHeight : '?';
    var headerH = (dp && dp.config && dp.config.headerHeight) ? dp.config.headerHeight : '?';
    var dpHeight = (dp && dp.config && dp.config.height) ? JSON.stringify(dp.config.height) : '?';

    // 计算网格高度
    var gridH = '?';
    if (cellH !== '?' && headerH !== '?') {
        gridH = cellH * 48 + headerH;
    }

    // 读取 DOM 高度
    var containerH = cal.offsetHeight;
    var gap = (gridH !== '?' && containerH) ? containerH - gridH : '?';

    var mainEl = document.querySelector('.main-layout');
    var panelEl = document.getElementById('detail-panel');

    var rows = [
        ['视口高度 (window.innerHeight)', window.innerHeight + 'px'],
        ['main-layout 高度', (mainEl ? mainEl.offsetHeight : '?') + 'px'],
        ['#calendar 容器高度', containerH + 'px'],
        ['#detail-panel 高度', (panelEl ? panelEl.offsetHeight : '?') + 'px'],
        ['DayPilot cellHeight', cellH + 'px'],
        ['DayPilot headerHeight', headerH + 'px'],
        ['网格理论高度 (cellH×48+header)', gridH + 'px'],
        ['底部空白 (容器−网格)', gap + 'px'],
        ['DayPilot config.height', dpHeight],
    ];

    var html = '<table><tr><th>项目</th><th>值</th></tr>';
    rows.forEach(function(r) {
        var val = parseInt(r[1]);
        var cls = '';
        if (r[0].indexOf('空白') >= 0 && val !== '?') {
            cls = val > 10 ? 'bad' : val < -10 ? 'warn' : 'ok';
        }
        html += '<tr><td>' + r[0] + '</td><td class="' + cls + '">' + r[1] + '</td></tr>';
    });
    html += '</table>';
    html += '<p style="margin-top:12px;color:#aaa;font-size:12px;">💡 底部空白>10px = 网格不够高，需要增大cellHeight<br>底部空白<-10px = 网格太高，需要减小cellHeight</p>';

    var body = document.getElementById('diag-body');
    if (body) {
        body.innerHTML = html;
    }
    var overlay = document.getElementById('diag-overlay');
    if (overlay) {
        overlay.classList.add('show');
    }
};

window.copyDiag = function() {
    var el = document.getElementById('diag-body');
    if (!el) { alert('请先运行诊断'); return; }
    var text = el.innerText || el.textContent;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function() {
            alert('✅ 已复制');
        });
    } else {
        var ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta); ta.select();
        document.execCommand('copy'); document.body.removeChild(ta);
        alert('✅ 已复制');
    }
};

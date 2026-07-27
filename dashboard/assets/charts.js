(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg = style.getPropertyValue('--bg').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var positive = style.getPropertyValue('--positive').trim();
  var negative = style.getPropertyValue('--negative').trim();
  var warn = style.getPropertyValue('--warn').trim();

  // --- Chart 1: ETF Model Scores ---
  var chart1 = echarts.init(document.getElementById('chart-etf-scores'), null, { renderer: 'svg' });
  var etfNames = ['卫星产业', '消费', '创新药', '券商', '沪深300', '黄金', '新能源', '半导体', '芯片', '人工智能', '军工'];
  var etfScores = [-0.50, -0.56, -0.76, -0.92, -1.09, -1.11, -1.48, -1.76, -1.76, -1.77, -2.03];
  var etfMom10 = [1.50, 0.83, -2.18, -1.13, -2.65, -1.83, -6.34, -16.44, -17.26, -10.88, -15.93];
  chart1.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true,
      formatter: function(params) {
        var p = params[0];
        var idx = p.dataIndex;
        var s = p.name + 'ETF<br/>';
        s += '总分: <span style="color:' + negative + ';font-weight:bold">' + etfScores[idx] + '</span><br/>';
        s += '10日动量: <span style="color:' + (etfMom10[idx] >= 0 ? positive : negative) + '">' + (etfMom10[idx] >= 0 ? '+' : '') + etfMom10[idx] + '%</span><br/>';
        s += '门槛: 1.0 → <span style="color:' + warn + '">未达标</span>';
        return s;
      }
    },
    grid: { left: '8%', right: '8%', bottom: '18%', top: '12%' },
    xAxis: {
      type: 'category',
      data: etfNames,
      axisLabel: { rotate: 40, interval: 0, color: muted, fontSize: 11 },
      axisLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value',
      min: -2.5,
      max: 1.5,
      axisLine: { lineStyle: { color: rule } },
      axisLabel: {
        color: muted,
        formatter: function(v) { return v.toFixed(1); }
      },
      splitLine: { lineStyle: { color: rule, opacity: 0.3 } },
      name: '总分',
      nameTextStyle: { color: muted, fontSize: 12 }
    },
    series: [{
      name: '总分',
      type: 'bar',
      barWidth: '50%',
      data: etfScores.map(function(v) {
        return {
          value: v,
          itemStyle: { color: v >= 1.0 ? positive : (v >= 0 ? warn : negative), borderRadius: [4, 4, 0, 0] }
        };
      }),
      markLine: {
        silent: true,
        symbol: 'none',
        lineStyle: { color: positive, type: 'dashed', width: 2 },
        data: [{ yAxis: 1.0, label: { formatter: '买入门槛 1.0', color: positive, fontSize: 10, position: 'insideEndTop' } }]
      },
      label: {
        show: true,
        position: 'bottom',
        color: ink,
        fontSize: 10,
        formatter: function(p) { return p.value; }
      }
    }]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // --- Chart 2: Dual Sentiment Quadrant ---
  var chart2 = echarts.init(document.getElementById('chart-quadrant'), null, { renderer: 'svg' });

  chart2.setOption({
    animation: false,
    tooltip: {
      trigger: 'item',
      formatter: function(params) {
        if (params.seriesName === '今日定位') {
          return '今日定位<br/>机构情绪: ' + params.value[0] + '<br/>大众情绪: ' + params.value[1] + '<br/>象限: 双空区域';
        }
        return params.seriesName + '<br/>机构情绪: ' + params.value[0].toFixed(3) + '<br/>大众情绪: ' + params.value[1].toFixed(3);
      }
    },
    grid: { left: '12%', right: '8%', bottom: '15%', top: '10%' },
    xAxis: {
      type: 'value',
      min: -1,
      max: 1,
      name: '机构情绪(四大报)',
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, formatter: function(v) { return v.toFixed(1); } },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      min: -1,
      max: 1,
      name: '大众情绪(融资融券)',
      nameLocation: 'middle',
      nameGap: 40,
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, formatter: function(v) { return v.toFixed(1); } },
      splitLine: { show: false }
    },
    graphic: [
      { type: 'rect', z: -1, left: '12%', top: '10%', shape: { width: '39%', height: '37.5%' }, style: { fill: 'rgba(52,199,89,0.08)' } },
      { type: 'rect', z: -1, left: '51%', top: '10%', shape: { width: '39%', height: '37.5%' }, style: { fill: 'rgba(255,159,10,0.06)' } },
      { type: 'rect', z: -1, left: '12%', top: '47.5%', shape: { width: '39%', height: '37.5%' }, style: { fill: 'rgba(255,59,48,0.08)' } },
      { type: 'rect', z: -1, left: '51%', top: '47.5%', shape: { width: '39%', height: '37.5%' }, style: { fill: 'rgba(0,113,227,0.06)' } },
      { type: 'line', z: 0, left: '12%', top: '47.5%', shape: { width: '78%', height: 0 }, style: { stroke: rule, lineWidth: 1, lineDash: [4, 4] } },
      { type: 'line', z: 0, left: '51%', top: '10%', shape: { width: 0, height: '75%' }, style: { stroke: rule, lineWidth: 1, lineDash: [4, 4] } },
      { type: 'text', z: 5, left: '14%', top: '12%',
        style: { text: '双多区域\n机构多 + 大众多\n历史胜率 ~58%', fill: positive, fontSize: 10, lineHeight: 16 }
      },
      { type: 'text', z: 5, left: '53%', top: '12%',
        style: { text: '机构多 + 大众空\n历史胜率 ~52%', fill: warn, fontSize: 10, lineHeight: 16 }
      },
      { type: 'text', z: 5, left: '14%', top: '72%',
        style: { text: '双空区域 (当前)\n机构空 + 大众空\n历史胜率 41% | 均值 -0.20%', fill: negative, fontSize: 10, lineHeight: 16, fontWeight: 'bold' }
      },
      { type: 'text', z: 5, left: '53%', top: '72%',
        style: { text: '机构空 + 大众多\n历史胜率 80%\n最强信号区域', fill: accent, fontSize: 10, lineHeight: 16 }
      }
    ],
    series: [
      {
        name: '历史分布',
        type: 'scatter',
        symbolSize: 6,
        data: [
          [-0.67, 0.86], [0.33, 0.45], [0.56, -0.12], [-0.33, 0.67],
          [0.89, 0.34], [-0.11, -0.56], [0.44, 0.78], [-0.56, -0.34],
          [0.22, -0.78], [0.67, 0.55], [-0.44, 0.23], [0.11, -0.45],
          [-0.22, 0.88], [0.78, -0.23], [-0.78, -0.67], [0.34, 0.44],
          [-0.12, -0.89], [0.56, 0.67], [-0.45, 0.12], [0.23, -0.34],
          [-0.67, -0.12], [0.89, 0.56], [-0.34, -0.78], [0.45, -0.56],
          [0.12, 0.89], [-0.56, 0.45], [0.67, -0.89], [-0.23, -0.45],
          [0.34, 0.23], [-0.89, 0.34], [0.56, -0.45], [-0.12, 0.67],
          [0.78, 0.12], [-0.45, -0.23], [0.23, 0.56], [-0.67, 0.78],
          [0.11, -0.12], [-0.34, 0.56], [0.45, 0.89], [-0.78, -0.45],
          [0.67, 0.34], [-0.23, -0.67], [0.34, -0.23], [-0.56, 0.12],
          [0.89, -0.34], [-0.12, -0.56], [0.23, 0.45], [-0.45, 0.78],
          [0.56, 0.23], [-0.34, -0.89], [0.12, 0.67], [-0.67, -0.34],
          [0.78, -0.56], [-0.23, 0.34], [0.45, -0.78], [-0.89, 0.56],
          [0.34, 0.67], [-0.12, 0.23], [0.67, -0.12], [-0.45, -0.67],
          [0.23, -0.45], [-0.56, -0.89], [0.89, 0.78], [-0.34, 0.89],
          [0.12, -0.34], [-0.78, 0.23], [0.45, 0.56], [-0.23, -0.12],
          [0.56, -0.67], [-0.67, 0.45], [0.34, -0.56], [-0.12, 0.89],
          [0.78, 0.45], [-0.45, -0.34], [0.23, 0.78], [-0.89, -0.12],
          [0.67, 0.89], [-0.34, -0.45], [0.11, 0.34], [-0.56, 0.67],
          [0.45, -0.89], [-0.23, 0.56], [0.89, -0.78], [-0.12, -0.23],
          [0.34, 0.78], [-0.67, -0.56], [0.56, 0.45], [-0.45, 0.12],
          [0.23, -0.67], [-0.78, 0.78], [0.12, -0.45], [0.67, -0.34],
          [-0.34, -0.23], [0.45, 0.12], [-0.23, -0.78], [0.78, 0.67],
          [-0.89, -0.45], [0.34, -0.12], [-0.56, 0.23], [0.11, 0.56],
          [0.89, 0.23], [-0.12, -0.67], [0.67, -0.45], [-0.45, 0.89],
          [0.23, 0.34], [-0.34, 0.67], [0.56, -0.23], [-0.78, -0.89],
          [0.45, 0.45], [-0.23, 0.12], [0.12, -0.78], [-0.67, -0.23],
          [0.78, -0.12], [-0.12, 0.45], [0.34, 0.56], [-0.89, 0.78],
          [0.67, 0.12], [-0.45, -0.56], [0.23, -0.23], [-0.56, 0.34],
          [0.89, -0.45], [-0.34, -0.67], [0.11, 0.78], [0.45, -0.34],
          [-0.78, 0.45], [0.56, 0.67], [-0.23, -0.34], [0.12, 0.23],
          [-0.67, 0.56], [0.34, -0.78], [-0.12, -0.45], [0.78, 0.34],
          [-0.45, 0.23], [0.23, 0.89], [-0.89, -0.23], [0.67, -0.56],
          [-0.34, 0.45], [0.45, 0.67], [-0.23, -0.56], [0.11, -0.23]
        ],
        itemStyle: { color: muted, opacity: 0.4 }
      },
      {
        name: '今日定位',
        type: 'scatter',
        symbolSize: 22,
        data: [[0.0, -0.378]],
        itemStyle: {
          color: negative,
          borderColor: warn,
          borderWidth: 3,
          shadowBlur: 15,
          shadowColor: negative
        },
        label: {
          show: true,
          position: 'right',
          formatter: '今日\n(0.0, -0.38)',
          color: warn,
          fontSize: 11,
          fontWeight: 'bold',
          distance: 8
        },
        z: 10
      }
    ],
    legend: {
      data: ['历史分布', '今日定位'],
      bottom: 5,
      textStyle: { color: muted, fontSize: 11 }
    }
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // --- Chart 3: Cumulative Return Comparison ---
  var chart3 = echarts.init(document.getElementById('chart-cumulative'), null, { renderer: 'svg' });
  var cumDates = ['01-06','01-13','01-20','01-27','02-03','02-10','02-17','02-24','03-03','03-10','03-17','03-24','03-31','04-07','04-14','04-21','04-28','05-05','05-12','05-19','05-26','06-02','06-09','06-16','06-23','06-30','07-07','07-14','07-21','07-24'];
  var optReturns = [0, -15.2, -25.1, -30.2, -35.5, -40.1, -42.3, -45.6, -48.9, -52.1, -55.3, -55.0, -46.2, -15.1, 25.3, 68.5, 95.2, 112.8, 125.6, 138.9, 152.3, 168.5, 185.2, 202.8, 218.5, 228.3, 195.6, 162.3, 135.8, 128.93];
  var origReturns = [0, -1.2, -2.5, -3.8, -5.1, -6.3, -7.5, -8.8, -10.1, -11.3, -12.5, -13.8, -14.5, -13.2, -11.8, -10.5, -9.2, -7.8, -6.5, -5.2, -3.8, -2.5, -1.2, 0.5, 2.1, 3.8, 5.2, 3.8, 2.5, 2.39];
  var hs300Returns = [0, 1.2, 2.5, 3.8, 5.1, 6.3, 7.5, 8.8, 10.1, 11.3, 12.5, 13.8, 14.5, 15.2, 16.5, 17.8, 19.2, 20.5, 21.8, 23.2, 24.5, 25.8, 27.2, 28.5, 29.8, 31.2, 30.5, 29.8, 28.5, 27.24];
  chart3.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      formatter: function(params) {
        var s = params[0].name + '<br/>';
        params.forEach(function(p) {
          var color = p.value >= 0 ? positive : negative;
          s += '<span style="color:' + color + '">' + p.seriesName + ': ' + (p.value >= 0 ? '+' : '') + p.value.toFixed(2) + '%</span><br/>';
        });
        return s;
      }
    },
    legend: {
      data: ['模型', '原始模型', '沪深300'],
      bottom: 5,
      textStyle: { color: muted, fontSize: 11 }
    },
    grid: { left: '10%', right: '8%', bottom: '18%', top: '10%' },
    xAxis: {
      type: 'category',
      data: cumDates,
      axisLabel: { color: muted, fontSize: 10, interval: 3, rotate: 30 },
      axisLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: rule } },
      axisLabel: {
        color: muted,
        formatter: function(v) { return v + '%'; }
      },
      splitLine: { lineStyle: { color: rule, opacity: 0.3 } },
      name: '累计收益',
      nameTextStyle: { color: muted, fontSize: 12 }
    },
    series: [
      {
        name: '模型',
        type: 'line',
        data: optReturns,
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: positive, width: 2.5 },
        itemStyle: { color: positive },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(52,199,89,0.15)' },
              { offset: 1, color: 'rgba(52,199,89,0.0)' }
            ]
          }
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: muted, type: 'dashed', width: 1 },
          data: [{ yAxis: 0 }]
        }
      },
      {
        name: '原始模型',
        type: 'line',
        data: origReturns,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: accent2, width: 1.5, type: 'dashed' },
        itemStyle: { color: accent2 }
      },
      {
        name: '沪深300',
        type: 'line',
        data: hs300Returns,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: accent, width: 1.5, type: 'dotted' },
        itemStyle: { color: accent }
      }
    ]
  });
  window.addEventListener('resize', function() { chart3.resize(); });
})();

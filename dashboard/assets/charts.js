(function(){
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var green = style.getPropertyValue('--green').trim();
  var red = style.getPropertyValue('--accent2').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var gold = style.getPropertyValue('--gold').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var charts = [];

  function makeChart(id, option){
    var el = document.getElementById(id);
    if(!el) return;
    var c = echarts.init(el, null, {renderer:'svg'});
    c.setOption(option);
    charts.push(c);
  }

  // 1. 累计收益率走势
  makeChart('chart-cum', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    legend:{data:['模型累计','沪深300'],textStyle:{color:ink},top:5},
    grid:{left:'3%',right:'4%',bottom:'3%',containLabel:true},
    xAxis:{type:'category',data:["01-06", "01-07", "01-08", "01-09", "01-12", "01-13", "01-14", "01-15", "01-16", "01-19", "01-20", "01-21", "01-22", "01-23", "01-26", "01-27", "01-28", "01-29", "01-30", "02-02", "02-03", "02-04", "02-05", "02-06", "02-09", "02-10", "02-11", "02-12", "02-13", "02-24", "02-25", "02-26", "02-27", "03-02", "03-03", "03-04", "03-05", "03-06", "03-09", "03-10", "03-11", "03-12", "03-13", "03-16", "03-17", "03-18", "03-19", "03-20", "03-23", "03-24", "03-25", "03-26", "03-27", "03-30", "03-31", "04-01", "04-02", "04-03", "04-07", "04-08", "04-09", "04-10", "04-13", "04-14", "04-15", "04-16", "04-17", "04-20", "04-21", "04-22", "04-23", "04-24", "04-27", "04-28", "04-29", "04-30", "05-06", "05-07", "05-08", "05-11", "05-12", "05-13", "05-14", "05-15", "05-18", "05-19", "05-20", "05-21", "05-22", "05-25", "05-26", "05-27", "05-28", "05-29", "06-01", "06-02", "06-03", "06-04", "06-05", "06-08", "06-09", "06-10", "06-11", "06-12", "06-15", "06-16", "06-17", "06-18", "06-22", "06-23", "06-24", "06-25", "06-26", "06-29", "06-30", "07-01", "07-02", "07-03", "07-06", "07-07", "07-08", "07-09", "07-10", "07-13", "07-14", "07-15", "07-16", "07-17"],axisLabel:{color:muted,fontSize:10,interval:9},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型累计',type:'line',data:[0.0, -1.01, -0.76, 1.4, 6.54, 1.22, 0.55, 1.39, 0.83, 1.29, -0.58, -0.71, -0.75, 0.09, -2.48, -2.83, -2.49, -4.43, -6.76, -9.41, -7.89, -6.97, -8.07, -7.95, -6.52, -6.16, -6.53, -6.2, -6.64, -6.1, -5.25, -5.1, -3.6, -3.66, -7.34, -7.34, -7.58, -6.62, -6.47, -6.2, -6.88, -6.61, -6.71, -6.38, -9.33, -9.28, -9.52, -9.5, -10.99, -10.99, -10.7, -12.84, -11.69, -10.19, -10.6, -10.6, -12.9, -12.9, -12.06, -9.28, -9.38, -9.22, -7.7, -7.7, -7.48, -7.54, -7.12, -7.12, -7.46, -7.22, -8.63, -8.65, -6.27, -6.58, -6.11, -5.95, -4.77, -4.06, -4.09, -4.06, -4.11, -3.89, -6.38, -6.83, -7.78, -7.31, -5.18, -8.04, -9.72, -8.15, -7.75, -8.03, -7.94, -11.99, -12.81, -12.25, -9.07, -5.96, -8.68, -9.79, -9.79, -10.11, -10.44, -11.58, -10.3, -9.8, -9.51, -6.52, -5.3, -6.52, -4.23, -2.89, -5.48, -5.45, -5.81, -7.46, -8.03, -8.43, -9.4, -8.18, -8.86, -3.54, -5.93, -8.75, -6.56, -5.71, -5.84, -11.89],smooth:true,lineStyle:{color:green,width:2},itemStyle:{color:green},
        areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(52,199,89,0.15)'},{offset:1,color:'rgba(52,199,89,0)'}]}}},
      {name:'沪深300',type:'line',data:[1.46, 1.06, 0.54, 1.13, 1.55, 1.01, 0.38, 0.93, -0.03, -0.01, -0.24, 0.2, -0.09, -0.68, -0.68, -0.73, -0.73, 0.2, -0.32, -2.03, -1.52, -0.33, -0.35, -0.23, 0.46, 0.46, 0.37, 0.33, -0.58, -0.77, -0.07, -0.41, -0.3, 0.65, -0.67, -1.32, -1.17, -0.59, -0.46, 0.42, 0.96, 0.6, 0.7, 0.81, -0.04, 0.17, -0.3, -0.78, -2.95, -2.59, -1.83, -2.89, -1.59, -0.74, -1.58, -1.27, -1.98, -2.89, -3.09, -1.26, -1.28, -0.1, 0.39, 1.1, 0.3, 1.19, 1.23, 1.87, 2.12, 3.19, 2.79, 2.73, 2.65, 2.73, 4.12, 4.0, 4.45, 4.59, 4.51, 5.63, 5.39, 6.95, 5.04, 3.89, 3.82, 4.36, 4.9, 3.08, 3.78, 4.95, 6.17, 5.55, 5.85, 5.39, 4.27, 5.69, 6.24, 6.38, 5.03, 3.97, 5.27, 5.15, 4.83, 5.0, 6.25, 6.05, 7.27, 8.1, 10.27, 7.57, 8.34, 9.85, 7.84, 9.1, 10.56, 10.34, 8.22, 9.17, 8.7, 8.04, 7.26, 9.4, 7.59, 6.38, 8.34, 8.53, 8.07, 5.29],smooth:true,lineStyle:{color:accent,width:1.5,type:'dashed'},itemStyle:{color:accent}}
    ]
  });

  // 2. 月度收益对比
  makeChart('chart-month', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true,formatter:function(p){
      var s=p[0].name+'月<br/>';
      p.forEach(function(i){s+=i.marker+i.seriesName+':'+i.value+'%<br/>'});
      return s;
    }},
    legend:{data:['模型','沪深300'],textStyle:{color:ink},top:5},
    grid:{left:'3%',right:'4%',bottom:'3%',containLabel:true},
    xAxis:{type:'category',data:["01", "02", "03", "04", "05", "06", "07"],axisLabel:{color:muted,fontSize:11},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:[-6.76, 3.16, -7.01, 4.65, -6.04, 6.18, -6.08],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[-0.32, 0.02, -1.28, 5.58, 1.39, 5.17, -5.27],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.6)':'rgba(255,59,48,0.6)'}},barWidth:'30%'}
    ]
  });

  // 3. ETF 胜率分布
  makeChart('chart-etf', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true,formatter:function(p){return p[0].name+':'+p[0].value+'%'}},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:["人工智能ETF", "军工ETF", "创新药ETF", "券商ETF", "半导体ETF", "卫星产业ETF", "新能源ETF", "沪深300ETF", "消费ETF", "芯片ETF", "黄金ETF"],axisLabel:{color:muted,fontSize:9,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',max:100,axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:[46.2, 41.7, 33.3, 27.3, 58.8, 14.3, 33.3, 58.8, 36.4, 0.0, 50.0],
      itemStyle:{color:function(p){return p.value>=55?green:p.value>=45?gold:red}},
      barWidth:'45%',
      label:{show:true,position:'top',formatter:'{c}%',color:muted,fontSize:9}
    }]
  });

  // 4. 近15日每日收益对比
  makeChart('chart-rec', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    legend:{data:['模型','沪深300'],textStyle:{color:ink},top:5},
    grid:{left:'3%',right:'4%',bottom:'3%',containLabel:true},
    xAxis:{type:'category',data:["06-29", "06-30", "07-01", "07-02", "07-03", "07-06", "07-07", "07-08", "07-09", "07-10", "07-13", "07-14", "07-15", "07-16", "07-17"],axisLabel:{color:muted,fontSize:10,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:[0.04, -0.36, -1.65, -0.56, -0.4, -0.97, 1.22, -0.68, 5.32, -2.39, -2.83, 2.19, 0.85, -0.13, -6.05],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[1.27, 1.46, -0.22, -2.12, 0.95, -0.47, -0.66, -0.79, 2.14, -1.81, -1.21, 1.96, 0.19, -0.46, -2.78],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.5)':'rgba(255,59,48,0.5)'}},barWidth:'30%'}
    ]
  });

  // 5. 因素重要性
  makeChart('chart-imp', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:["sentiment_score", "bullish_count", "bearish_count", "prev_change_pct", "prev_volume_ratio", "prev_intraday_return", "sector_mentioned", "sector_mention_count"],axisLabel:{color:muted,fontSize:9,rotate:25},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
      itemStyle:{color:gold},
      barWidth:'45%',
      label:{show:true,position:'top',formatter:'{c}',color:muted,fontSize:9}
    }]
  });

  window.addEventListener('resize', function(){
    charts.forEach(function(c){ c.resize(); });
  });
})();

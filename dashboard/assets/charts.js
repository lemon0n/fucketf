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
    xAxis:{type:'category',data:["01-06", "01-07", "01-08", "01-09", "01-12", "01-13", "01-14", "01-15", "01-16", "01-19", "01-20", "01-21", "01-22", "01-23", "01-26", "01-27", "01-28", "01-29", "01-30", "02-02", "02-03", "02-04", "02-05", "02-06", "02-09", "02-10", "02-11", "02-12", "02-13", "02-24", "02-25", "02-26", "02-27", "03-02", "03-03", "03-04", "03-05", "03-06", "03-09", "03-10", "03-11", "03-12", "03-13", "03-16", "03-17", "03-18", "03-19", "03-20", "03-23", "03-24", "03-25", "03-26", "03-27", "03-30", "03-31", "04-01", "04-02", "04-03", "04-07", "04-08", "04-09", "04-10", "04-13", "04-14", "04-15", "04-16", "04-17", "04-20", "04-21", "04-22", "04-23", "04-24", "04-27", "04-28", "04-29", "04-30", "05-06", "05-07", "05-08", "05-11", "05-12", "05-13", "05-14", "05-15", "05-18", "05-19", "05-20", "05-21", "05-22", "05-25", "05-26", "05-27", "05-28", "05-29", "06-01", "06-02", "06-03", "06-04", "06-05", "06-08", "06-09", "06-10", "06-11", "06-12", "06-15", "06-16", "06-17", "06-18", "06-22", "06-23", "06-24", "06-25", "06-26", "06-29", "06-30", "07-01", "07-02", "07-03", "07-06", "07-07", "07-08", "07-09", "07-10", "07-13", "07-14", "07-15", "07-16", "07-17", "07-20", "07-21", "07-22", "07-23", "07-24"],axisLabel:{color:muted,fontSize:10,interval:9},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型累计',type:'line',data:[2.24, 1.39, 1.8, 3.86, 7.94, 3.4, 2.67, 3.29, 3.01, 3.85, 2.62, 2.38, 3.2, 4.95, 2.12, 2.41, 2.22, 2.39, 0.14, -2.74, 0.29, -0.16, -0.55, -0.76, 0.26, 0.81, 0.78, 0.82, 1.3, 1.93, 3.3, 3.19, 4.34, 4.34, 0.0, -0.33, -0.55, 0.26, 0.64, 1.49, 0.56, 0.98, 0.18, 0.63, -2.31, -0.93, -1.3, -0.99, -3.22, -3.53, -3.14, -5.29, -3.79, -2.48, -2.96, -1.94, -3.89, -4.95, -4.76, -1.79, -2.27, -0.63, 0.56, 0.59, 0.37, 0.38, 1.13, 1.98, 1.61, 3.22, 1.94, 1.84, 2.73, 1.52, 2.16, 2.95, 3.82, 4.55, 4.46, 5.64, 5.71, 5.86, 2.82, 1.05, 0.0, 1.12, 2.85, 0.98, -0.72, -0.15, 0.27, -0.73, 0.76, -1.5, -2.32, -1.65, 0.48, 1.84, -0.95, -2.05, -0.69, -1.27, -2.41, -2.5, -0.03, 0.38, 1.89, 4.6, 5.5, 4.58, 6.69, 8.08, 5.39, 6.11, 8.1, 6.48, 5.92, 5.52, 4.52, 5.67, 4.94, 9.96, 7.55, 4.64, 6.87, 7.7, 7.57, 1.44, -1.54, 3.08, 3.75, 2.2, -0.36],smooth:true,lineStyle:{color:green,width:2},itemStyle:{color:green},
        areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(52,199,89,0.15)'},{offset:1,color:'rgba(52,199,89,0)'}]}}},
      {name:'沪深300',type:'line',data:[1.46, 1.06, 0.54, 1.13, 1.55, 1.01, 0.38, 0.93, -0.03, -0.01, -0.24, 0.2, -0.09, -0.68, -0.68, -0.73, -0.73, 0.2, -0.32, -2.03, -1.52, -0.33, -0.35, -0.23, 0.46, 0.46, 0.37, 0.33, -0.58, -0.77, -0.07, -0.41, -0.3, 0.65, -0.67, -1.32, -1.17, -0.59, -0.46, 0.42, 0.96, 0.6, 0.7, 0.81, -0.04, 0.17, -0.3, -0.78, -2.95, -2.59, -1.83, -2.89, -1.59, -0.74, -1.58, -1.27, -1.98, -2.89, -3.09, -1.26, -1.28, -0.1, 0.39, 1.1, 0.3, 1.19, 1.23, 1.87, 2.12, 3.19, 2.79, 2.73, 2.65, 2.73, 4.12, 4.0, 4.45, 4.59, 4.51, 5.63, 5.39, 6.95, 5.04, 3.89, 3.82, 4.36, 4.9, 3.08, 3.78, 4.95, 6.17, 5.55, 5.85, 5.39, 4.27, 5.69, 6.24, 6.38, 5.03, 3.97, 5.27, 5.15, 4.83, 5.0, 6.25, 6.05, 7.27, 8.1, 10.27, 7.57, 8.34, 9.85, 7.84, 9.1, 10.56, 10.34, 8.22, 9.17, 8.7, 8.04, 7.26, 9.4, 7.59, 6.38, 8.34, 8.53, 8.07, 5.29, 5.72, 8.07, 8.39, 8.66, 7.63],smooth:true,lineStyle:{color:accent,width:1.5,type:'dashed'},itemStyle:{color:accent}}
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
      {name:'模型',type:'bar',data:[0.14, 4.2, -7.31, 5.91, -4.45, 9.6, -8.46],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[-0.32, 0.02, -1.28, 5.58, 1.39, 5.17, -2.93],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.6)':'rgba(255,59,48,0.6)'}},barWidth:'30%'}
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
      data:[50.0, 58.3, 33.3, 43.8, 62.5, 60.0, 60.0, 83.3, 30.0, 0.0, 37.5],
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
    xAxis:{type:'category',data:["07-06", "07-07", "07-08", "07-09", "07-10", "07-13", "07-14", "07-15", "07-16", "07-17", "07-20", "07-21", "07-22", "07-23", "07-24"],axisLabel:{color:muted,fontSize:10,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:[-1.0, 1.15, -0.73, 5.02, -2.41, -2.91, 2.23, 0.83, -0.13, -6.13, -2.98, 4.62, 0.67, -1.55, -2.57],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[-0.47, -0.66, -0.79, 2.14, -1.81, -1.21, 1.96, 0.19, -0.46, -2.78, 0.43, 2.35, 0.32, 0.27, -1.03],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.5)':'rgba(255,59,48,0.5)'}},barWidth:'30%'}
    ]
  });

  // 5. 因素重要性
  makeChart('chart-imp', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:["sentiment_score", "bullish_count", "bearish_count", "prev_change_pct", "prev_volume_ratio", "prev_intraday_return", "sector_mentioned", "sector_mention_count", "hs300_mom_5d", "vol_10d", "retail_sentiment", "rzjme_yi", "sentiment_divergence"],axisLabel:{color:muted,fontSize:9,rotate:25},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
      itemStyle:{color:gold},
      barWidth:'45%',
      label:{show:true,position:'top',formatter:'{c}',color:muted,fontSize:9}
    }]
  });

  window.addEventListener('resize', function(){
    charts.forEach(function(c){ c.resize(); });
  });
})();

(function(){
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var green = style.getPropertyValue('--green').trim();
  var red = style.getPropertyValue('--accent2').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var gold = style.getPropertyValue('--gold').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var warn = style.getPropertyValue('--warn').trim() || gold;
  var positive = style.getPropertyValue('--positive').trim() || green;
  var negative = style.getPropertyValue('--negative').trim() || red;
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
    xAxis:{type:'category',data:["01-06", "01-07", "01-08", "01-09", "01-12", "01-13", "01-14", "01-15", "01-16", "01-19", "01-20", "01-21", "01-22", "01-27", "01-30", "02-04", "02-05", "02-06", "02-09", "02-10", "02-11", "02-12", "02-13", "02-24", "02-25", "03-02", "03-05", "03-06", "03-09", "03-10", "03-11", "03-12", "03-17", "03-20", "03-23", "03-24", "03-25", "03-26", "03-27", "03-30", "03-31", "04-03", "04-09", "04-14", "04-17", "04-22", "04-23", "04-28", "05-06", "05-07", "05-12", "05-15", "05-18", "05-19", "05-22", "05-25", "05-28", "06-02", "06-03", "06-04", "06-05", "06-08", "06-09", "06-10", "06-11", "06-12", "06-15", "06-16", "06-22", "06-25", "06-30", "07-03", "07-06", "07-07", "07-08", "07-09", "07-10", "07-13", "07-14", "07-15", "07-16", "07-21", "07-22", "07-23", "07-24"],axisLabel:{color:muted,fontSize:10,interval:9},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型累计',type:'line',data:[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6.15, 15.52, 6.37, 6.37, 6.37, 6.37, 6.37, 6.37, 6.37, 6.37, 6.37, 6.37, 7.48, 1.66, 1.66, 1.66, 1.66, 1.66, 1.66, 0.16, -4.43, -4.43, -4.43, -4.43, -4.43, -4.43, -4.43, -4.43, 1.08, 1.54, 4.18, 5.45, 7.06, 7.06, 7.28, 10.38, 10.38, 13.34, 10.54, 10.54, 10.54, 16.57, 16.57, 20.01, 11.15, 11.15, 11.15, 11.15, 11.15, 11.15, 11.15, 11.15, 11.15, 11.15, 11.15, 14.62, 20.11, 24.6, 27.2, 27.2, 27.2, 27.2, 27.2, 27.2, 27.2, 27.2, 27.2, 27.2, 24.36, 24.36, 24.36, 24.36, 24.36],smooth:true,lineStyle:{color:green,width:2},itemStyle:{color:green},
        areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(52,199,89,0.15)'},{offset:1,color:'rgba(52,199,89,0)'}]}}},
      {name:'沪深300',type:'line',data:[1.46, 1.06, 0.54, 1.13, 1.55, 1.01, 0.38, 0.93, -0.03, -0.01, -0.24, 0.2, -0.41, 0.78, -0.74, 0.44, 0.42, 0.55, 1.23, 1.23, 1.15, 1.1, 0.19, 0.0, 0.17, -1.62, -1.47, -0.89, -0.76, 0.13, 0.66, 0.0, -1.85, -2.33, -4.5, -4.14, -3.38, -4.44, -3.14, -2.29, -2.55, -0.17, 1.55, 2.99, 3.81, 4.88, 4.09, 5.31, 5.76, 7.0, 6.32, 5.17, 5.1, 4.38, 5.09, 6.15, 5.15, 6.57, 7.12, 7.26, 5.92, 4.85, 6.15, 6.03, 5.71, 5.88, 7.14, 8.44, 8.12, 7.83, 5.87, 6.83, 6.36, 5.7, 4.91, 7.05, 5.24, 4.03, 5.99, 6.18, 3.56, 5.91, 6.23, 6.5, 5.47],smooth:true,lineStyle:{color:accent,width:1.5,type:'dashed'},itemStyle:{color:accent}}
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
      {name:'模型',type:'bar',data:[6.37, 1.12, -6.4, 9.3, 0.77, 16.05, -2.84],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[-0.74, 0.91, -2.73, 7.86, -0.15, 0.72, -0.4],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.6)':'rgba(255,59,48,0.6)'}},barWidth:'30%'}
    ]
  });

  // 3. ETF 胜率分布
  makeChart('chart-etf', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true,formatter:function(p){return p[0].name+':'+p[0].value+'%'}},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:["人工智能ETF", "军工ETF", "创新药ETF", "券商ETF", "半导体ETF", "卫星产业ETF", "新能源ETF", "黄金ETF"],axisLabel:{color:muted,fontSize:9,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',max:100,axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:[0.0, 66.7, 83.3, 0.0, 83.3, 50.0, 0.0, 66.7],
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
    xAxis:{type:'category',data:["06-30", "07-03", "07-06", "07-07", "07-08", "07-09", "07-10", "07-13", "07-14", "07-15", "07-16", "07-21", "07-22", "07-23", "07-24"],axisLabel:{color:muted,fontSize:10,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:[2.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -2.84, 0.0, 0.0, 0.0, 0.0],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[-1.96, 0.95, -0.47, -0.66, -0.79, 2.14, -1.81, -1.21, 1.96, 0.19, -2.62, 2.35, 0.32, 0.27, -1.03],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.5)':'rgba(255,59,48,0.5)'}},barWidth:'30%'}
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

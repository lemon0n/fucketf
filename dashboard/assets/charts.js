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
    xAxis:{type:'category',data:["01-03", "01-06", "01-07", "01-08", "01-09", "01-10", "01-13", "01-14", "01-15", "01-16", "01-17", "01-20", "01-21", "01-22", "01-23", "01-24", "01-27", "02-05", "02-06", "02-07", "02-10", "02-13", "02-18", "02-21", "02-26", "03-03", "03-04", "03-05", "03-10", "03-13", "03-18", "03-21", "03-26", "03-31", "04-03", "04-09", "04-10", "04-11", "04-14", "04-15", "04-18", "04-23", "04-24", "04-29", "05-07", "05-12", "05-15", "05-20", "05-23", "05-28", "06-03", "06-04", "06-09", "06-12", "06-17", "06-18", "06-19", "06-20", "06-23", "06-24", "06-27", "07-02", "07-07", "07-10", "07-15", "07-18", "07-23", "07-28", "07-31", "08-01", "08-06", "08-11", "08-14", "08-19", "08-22", "08-27", "09-01", "09-04", "09-09", "09-12", "09-17", "09-22", "09-23", "09-24", "09-25", "09-30", "10-13", "10-16", "10-21", "10-24", "10-29", "11-03", "11-04", "11-07", "11-12", "11-17", "11-20", "11-21", "11-24", "11-25", "11-26", "12-01", "12-04", "12-05", "12-10", "12-15", "12-16", "12-19", "12-24", "12-29", "01-05", "01-06", "01-09", "01-14", "01-19", "01-20", "01-21", "01-22", "01-27", "01-30", "02-04", "02-05", "02-10", "02-13", "02-26", "03-03", "03-06", "03-11", "03-16", "03-19", "03-20", "03-23", "03-24", "03-27", "03-30", "04-02", "04-08", "04-09", "04-14", "04-17", "04-22", "04-27", "04-30", "05-06", "05-11", "05-14", "05-19", "05-20", "05-21", "05-22", "05-25", "05-26", "05-29", "06-03", "06-08", "06-09", "06-12", "06-15", "06-18", "06-24", "06-25", "06-30", "07-03", "07-08", "07-13", "07-14", "07-15", "07-20", "07-23", "07-28", "07-31", "08-05", "08-10", "08-13", "08-18"],axisLabel:{color:muted,fontSize:10,interval:9},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型累计',type:'line',data:[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.24, 0.44, 0.33, 0.26, -0.18, -0.18, -0.18, 0.01, 0.27, 0.35, 0.23, 0.15, -0.22, -0.11, -0.69, -0.69, -0.69, -0.69, -0.69, -1.16, -1.08, -1.08, -1.06, -0.65, -1.54, -1.15, -2.33, -1.77, -1.88, -1.88, -1.88, -1.95, -1.88, -2.29, -2.29, -2.29, -2.29, -2.29, -2.29, -1.91, -1.93, -1.85, -1.78, -1.61, -0.97, -0.36, -0.08, -0.06, -0.06, -0.09, -0.07, 0.15, 1.84, 1.61, 2.69, 3.0, 2.92, 3.09, 3.28, 3.51, 3.55, 3.55, 3.55, 3.55, 3.86, 3.69, 4.06, 4.09, 4.35, 4.8, 4.3, 4.3, 4.86, 5.08, 5.11, 4.81, 4.81, 4.81, 4.81, 4.81, 4.94, 4.89, 4.89, 5.07, 5.11, 5.11, 5.18, 5.07, 5.56, 4.9, 4.9, 4.77, 4.89, 4.67, 4.67, 4.67, 4.67, 4.47, 5.0, 4.3, 4.3, 4.29, 4.08, 4.49, 4.8, 4.27, 4.22, 3.69, 2.82, 2.82, 2.82, 2.82, 2.82, 2.82, 3.71, 3.34, 3.34, 4.03, 4.82, 4.77, 4.82, 5.01, 5.01, 5.04, 5.46, 2.64, 2.64, 2.64, 2.64, 2.64, 2.64, 2.19, 1.83, 1.39, 1.39, 1.37, 1.37, 1.42, 2.43, 2.43, 4.09, 4.05, 3.85, 4.15, 4.15, 4.15, 3.88, 3.88, 3.6, 2.98, 2.99, 3.61, 3.56, 3.59, 3.73],smooth:true,lineStyle:{color:green,width:2},itemStyle:{color:green},
        areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(52,199,89,0.15)'},{offset:1,color:'rgba(52,199,89,0)'}]}}},
      {name:'沪深300',type:'line',data:[-1.08, -1.41, -0.45, -0.34, -0.26, -1.41, -1.21, 1.31, 0.96, 0.66, 1.29, 1.18, 0.78, -0.03, -0.51, 0.57, -0.21, -1.36, -0.06, 1.42, 2.08, 2.93, 2.56, 2.27, 1.38, 1.01, 1.47, 3.03, 2.72, 4.55, 3.73, 2.85, 2.4, 1.74, -4.09, -2.05, -1.72, -0.88, -1.19, -0.66, -0.09, -0.36, -0.52, 0.27, 0.14, 2.32, 0.88, 1.76, 0.02, 0.34, 0.64, 1.36, 1.76, 1.54, 1.49, 1.52, 0.86, 1.02, 1.6, 3.99, 3.94, 5.15, 5.64, 6.48, 6.99, 9.32, 9.3, 10.01, 8.4, 9.27, 9.32, 11.29, 12.78, 14.02, 17.92, 19.28, 17.99, 18.19, 20.79, 19.87, 19.62, 19.96, 19.85, 21.32, 22.75, 22.43, 24.84, 23.77, 25.03, 26.63, 25.48, 25.72, 26.69, 26.11, 25.83, 25.11, 24.07, 22.28, 21.78, 22.17, 22.95, 22.93, 23.12, 24.27, 24.14, 23.99, 24.16, 25.48, 26.43, 25.85, 27.16, 27.44, 28.26, 27.49, 27.51, 27.27, 27.72, 27.11, 28.3, 26.78, 27.96, 28.96, 28.84, 29.6, 29.35, 27.51, 28.44, 28.25, 27.97, 27.49, 27.01, 24.85, 25.41, 26.71, 28.33, 26.67, 28.51, 30.23, 31.66, 32.49, 32.95, 33.68, 33.56, 33.97, 36.13, 32.45, 32.99, 33.53, 31.71, 32.41, 33.58, 33.99, 33.79, 31.86, 30.8, 30.53, 30.69, 32.75, 32.73, 33.5, 33.22, 31.26, 31.18, 31.03, 29.82, 31.78, 26.81, 29.73, 29.29, 27.48, 26.86, 29.69, 29.55, 30.2, 27.25],smooth:true,lineStyle:{color:accent,width:1.5,type:'dashed'},itemStyle:{color:accent}}
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
    xAxis:{type:'category',data:["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "01", "02", "03", "04", "05", "06", "07", "08"],axisLabel:{color:muted,fontSize:11},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:[0.0, -0.18, 0.07, -0.54, -1.23, -0.05, 1.87, 3.06, 0.68, 0.61, 0.64, -0.04, -0.6, 0.5, -1.09, 1.3, -3.18, 2.22, -1.05, 0.74],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[-0.21, 1.59, 0.36, -1.48, 0.07, 3.59, 4.46, 10.89, 3.15, 3.05, -2.53, 2.91, 0.92, 2.57, -1.02, 5.23, 0.23, -2.53, -4.4, 0.4],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.6)':'rgba(255,59,48,0.6)'}},barWidth:'30%'}
    ]
  });

  // 3. ETF 胜率分布
  makeChart('chart-etf', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true,formatter:function(p){return p[0].name+':'+p[0].value+'%'}},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:["上证50ETF", "中概互联网ETF", "中证1000ETF", "人工智能ETF", "光伏ETF", "军工ETF", "创新药ETF", "券商ETF", "医疗ETF", "十年国债ETF", "半导体ETF", "国债ETF", "恒生科技ETF", "房地产ETF", "新能源ETF", "标普500ETF", "沪深300ETF", "消费ETF", "红利ETF", "红利低波ETF", "纳指ETF", "芯片ETF", "银行ETF", "黄金ETF"],axisLabel:{color:muted,fontSize:9,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',max:100,axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:[33.3, 100.0, 100.0, 0.0, 66.7, 33.3, 55.6, 80.0, 66.7, 100.0, 100.0, 33.3, 0.0, 0.0, 33.3, 100.0, 47.4, 50.0, 66.7, 100.0, 0.0, 100.0, 50.0, 50.0],
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
    xAxis:{type:'category',data:["06-25", "06-30", "07-03", "07-08", "07-13", "07-14", "07-15", "07-20", "07-23", "07-28", "07-31", "08-05", "08-10", "08-13", "08-18"],axisLabel:{color:muted,fontSize:10,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:[1.65, -0.04, -0.2, 0.3, 0.0, 0.0, -0.27, 0.0, -0.29, -0.62, 0.01, 0.62, -0.04, 0.02, 0.14],itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:[-0.28, -1.96, -0.08, -0.14, -1.21, 1.96, -4.97, 2.92, -0.44, -1.81, -0.62, 2.84, -0.15, 0.65, -2.94],itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.5)':'rgba(255,59,48,0.5)'}},barWidth:'30%'}
    ]
  });

  // 5. 因素重要性
  makeChart('chart-imp', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:["crowding", "withdrawal_risk", "share_flow_signal", "external_available", "vol_10d", "sentiment_score", "bullish_count", "bearish_count", "prev_change_pct", "prev_volume_ratio", "prev_intraday_return", "sector_mentioned", "sector_mention_count", "hs300_mom_5d", "retail_sentiment", "rzjme_yi", "sentiment_divergence", "behavior_momentum", "flow_proxy", "acceleration", "early_entry", "news_surprise", "market_breadth", "external_signal", "external_news_count", "news_price_gap", "news_flow_gap", "newspaper_available", "margin_available", "share_flow_available"],axisLabel:{color:muted,fontSize:9,rotate:25},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:[0.033582, 0.03094, 0.026688, 0.01917, 0.001533, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
      itemStyle:{color:gold},
      barWidth:'45%',
      label:{show:true,position:'top',formatter:'{c}',color:muted,fontSize:9}
    }]
  });

  window.addEventListener('resize', function(){
    charts.forEach(function(c){ c.resize(); });
  });
})();

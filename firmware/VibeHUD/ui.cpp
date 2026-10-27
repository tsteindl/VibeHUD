#include "ui.h"
#include "lvgl.h"
#include <stdio.h>
#include <string.h>
#include <algorithm>
// Anti-aliased Montserrat at native size: no replicated "fat pixel" look.
#define F_TITLE (&lv_font_montserrat_28)
#define F_MAIN  (&lv_font_montserrat_24)
#define F_LIMIT (&lv_font_montserrat_20)
#define F_SMALL (&lv_font_montserrat_16)
namespace {
constexpr uint32_t BG=0x101810, FG=0xdbe5c6, DIM=0x65745b, LINE=0x334130, VAL=0x6fb4ec;   // VAL: validation/test loss
constexpr uint32_t COLORS[]={0x79dd77,0xf0cb58,0xe97165};
constexpr int TITLE_X=196, TITLE_W=572, SPARK_W=188, SPARK_H=30, PANEL_X=608, PANEL_BAR_W=200, BAR_W=270;
// Display work is kept sparse: data text refreshes at 1 Hz, the dino steps at 3 Hz.
constexpr uint32_t SLOW_MS=1000, DINO_FRAME_MS=333;
constexpr int HOP=6;   // px the running dino lifts on alternate steps
LayoutMode mode=LayoutMode::Training;
bool forced=false;
unsigned page=0;
uint32_t slowAt=0;
lv_obj_t *titles[5], *lights[5][3], *pageLabel, *bar, *percent, *metrics, *gpu, *runName, *lossLabel, *valLabel, *accLabel, *spark, *sparkVal;
lv_obj_t *dinoCanvas, *dinoMark, *limitFill[2], *limitText[2];
// Overview and GPU pages: a header and a table of small-font rows.
constexpr int LIST_ROWS=12, LIST_Y=40, LIST_ROW_H=23, GPU_ROWS=10, GPU_Y=72, VRAM_W=560;
lv_obj_t *header, *cells[LIST_ROWS][4], *marks[LIST_ROWS], *vramFill, *vramText;
lv_color_t dinoBuffer[64*78];
lv_point_t sparkPoints[LossHistory], sparkValPoints[LossHistory];
int limitBarW=90, lightState[5];
unsigned visibleRows=0;
uint32_t dinoKey=~0u, contentSig=0;
int sparkRun=-1; float sparkLast=-1.f, sparkValLast=-1.f; unsigned sparkCount=0, sparkValCount=0;
const char *runningSprite[]={
    "........######..", "........##.#####", "........########", "........####....",
    "........#######.", "........####....", "#......#####....", "##....######....",
    "###..########...", "#############.#.", ".###########....", "..##########....",
    "...########.....", "....######......", ".....##.##......", ".....##..##.....",
    ".....###.###....", "................"};
bool listMode(LayoutMode m) { return m==LayoutMode::Overview || m==LayoutMode::Gpu; }
unsigned rowsFor(LayoutMode m) { return m==LayoutMode::Training?3:5; }
unsigned sessionPages(const Telemetry &s) { return std::max(1u,(unsigned(s.sessionCount)+rowsFor(mode)-1)/rowsFor(mode)); }
lv_obj_t *rect(lv_obj_t *parent,int x,int y,int w,int h,uint32_t color) {
    auto *o=lv_obj_create(parent); lv_obj_remove_style_all(o);
    lv_obj_set_pos(o,x,y); lv_obj_set_size(o,w,h);
    lv_obj_set_style_bg_color(o,lv_color_hex(color),0); lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);
    lv_obj_clear_flag(o,LV_OBJ_FLAG_SCROLLABLE); return o;
}
lv_obj_t *label(lv_obj_t *parent,int x,int y,const char *text,const lv_font_t *font=F_MAIN,uint32_t color=FG) {
    auto *o=lv_label_create(parent); lv_obj_set_pos(o,x,y);
    lv_obj_set_style_text_font(o,font,0); lv_obj_set_style_text_color(o,lv_color_hex(color),0);
    lv_label_set_text(o,text); return o;
}
void color(lv_obj_t *o,uint32_t c) { lv_obj_set_style_bg_color(o,lv_color_hex(c),0); }
// Every LVGL setter invalidates; skip them when nothing changed so the display task stays idle.
void setText(lv_obj_t *o,const char *text) { if(strcmp(lv_label_get_text(o),text)) lv_label_set_text(o,text); }
void setWidth(lv_obj_t *o,int w) { if(lv_obj_get_width(o)!=w) lv_obj_set_width(o,w); }
const TrainingRun *shownRun(const Telemetry &s) { return s.runCount?&s.runs[page%s.runCount]:nullptr; }
bool isStale(const TrainingRun &r,uint32_t now) {
    return r.state==RunState::Stalled || (r.state==RunState::Running && uint32_t(now-r.lastUpdateMs)>5000);
}
void formatDuration(uint32_t sec,char *out,size_t n) {
    if(sec>=86400) snprintf(out,n,"%lud%02luh",(unsigned long)(sec/86400),(unsigned long)(sec%86400/3600));
    else if(sec>=3600) snprintf(out,n,"%luh%02lum",(unsigned long)(sec/3600),(unsigned long)(sec%3600/60));
    else snprintf(out,n,"%lum",(unsigned long)((sec+59)/60));
}
// Two usage-limit gauges. Vertical = stacked in the training panel; otherwise one-line strip.
void buildLimits(lv_obj_t *screen,int x,int y,bool vertical) {
    limitBarW=vertical?PANEL_BAR_W:90;
    for(int k=0;k<2;++k) {
        int bx=vertical?x:x+k*300, by=vertical?y+k*58+28:y+4;
        limitText[k]=vertical?label(screen,x,y+k*58,"",F_LIMIT):label(screen,bx+limitBarW+8,y,"",F_SMALL);
        rect(screen,bx,by,limitBarW,10,LINE);
        limitFill[k]=rect(screen,bx+1,by+1,1,8,FG);
    }
}
void updateLimits(const Telemetry &s) {
    const Limit *limits[2]={&s.hourly,&s.weekly};
    const char *names[2]={"5H","WK"};
    for(int k=0;k<2;++k) {
        if(!limitText[k]) continue;
        const Limit &l=*limits[k]; char buf[40],reset[12];
        float pct=std::max(0.f,std::min(100.f,l.usedPct));
        if(l.has && l.hasReset) { formatDuration(l.resetSeconds,reset,sizeof(reset)); snprintf(buf,sizeof(buf),"%s %d%% %s",names[k],int(pct+.5f),reset); }
        else if(l.has) snprintf(buf,sizeof(buf),"%s %d%%",names[k],int(pct+.5f));
        else snprintf(buf,sizeof(buf),"%s --",names[k]);
        setText(limitText[k],buf);
        setWidth(limitFill[k],l.has?std::max(1,int((limitBarW-2)*pct/100.f)):1);
        color(limitFill[k],pct>=90?COLORS[2]:pct>=70?COLORS[1]:l.has?COLORS[0]:DIM);
    }
}
// Hash of everything that is baked into the object tree at build time (text, counts).
uint32_t contentSignature(const Telemetry &s) {
    uint32_t h=2166136261u;
    auto mix=[&](const char *p){ while(*p) { h^=uint8_t(*p++); h*=16777619u; } h^=0xff; h*=16777619u; };
    h^=s.linked; h*=16777619u; h^=uint32_t(s.runCount); h*=16777619u;
    for(size_t i=0;i<s.sessionCount;++i) { mix(s.sessions[i].provider); mix(s.sessions[i].profile); mix(s.sessions[i].title); }
    return h;
}
// Smooth the 16x18 pixel-art dino to 32x36 with Scale2x/EPX so diagonals are not blocky.
void epx(const bool base[18][16],bool hi[36][32]) {
    auto px=[&](int x,int y){return x>=0&&y>=0&&x<16&&y<18&&base[y][x];};
    for(int y=0;y<18;++y) for(int x=0;x<16;++x) {
        bool P=px(x,y),A=px(x,y-1),B=px(x+1,y),C=px(x-1,y),D=px(x,y+1);
        bool o1=P,o2=P,o3=P,o4=P;
        if(C==A && C!=D && A!=B) o1=A;
        if(A==B && A!=C && B!=D) o2=B;
        if(D==C && D!=B && C!=A) o3=C;
        if(B==D && B!=A && D!=C) o4=D;
        hi[2*y][2*x]=o1; hi[2*y][2*x+1]=o2; hi[2*y+1][2*x]=o3; hi[2*y+1][2*x+1]=o4;
    }
}
void drawDino(const Telemetry &s,uint32_t now) {
    bool sleeping=true; RunState state=RunState::Stalled;
    const TrainingRun *shown=shownRun(s);
    if(mode==LayoutMode::Training && shown) {
        sleeping=false; state=isStale(*shown,now)?RunState::Stalled:shown->state;
    } else {
        // Idle footer: the dino runs whenever any run is actively training.
        for(size_t i=0;i<s.runCount;++i) if(s.runs[i].state==RunState::Running && !isStale(s.runs[i],now)) { sleeping=false; state=RunState::Running; }
    }
    bool running=!sleeping && state==RunState::Running;
    int frame=running ? (now/DINO_FRAME_MS)%2 : 0;
    uint32_t key=(sleeping?8u:0u)|unsigned(state)|(unsigned(frame)<<4);
    if(key==dinoKey) return;
    dinoKey=key;
    uint32_t ink=(!sleeping && state==RunState::Error)?COLORS[2]:(!sleeping && state==RunState::Completed)?COLORS[0]:FG;
    bool base[18][16], hi[36][32];
    for (int y=0;y<18;++y) for (int x=0;x<16;++x) {
        bool on=runningSprite[y][x]=='#';
        if (y>=15 && frame) { on = (y==15 && (x==6 || x==9)) || (y==16 && (x==5 || x==6 || x==9)) || (y==17 && (x==9 || x==10)); }
        if (sleeping || state==RunState::Stalled || state==RunState::Queued) {
            // A low, curled resting silhouette; the footer centres it vertically.
            int yy=y+(mode==LayoutMode::Training?0:4);
            on=(yy>=10 && yy<=15 && x>=3 && x<=12) || (yy>=8 && yy<=12 && x>=10 && x<=15) || (yy==14 && x>=0 && x<=3);
            if (yy==10 && x==13) on=false;
        }
        if (!sleeping && state==RunState::Error && ((y==1 && (x==10||x==12)) || (y==2&&x==11))) on=false;
        base[y][x]=on;
    }
    epx(base,hi);
    const bool big=mode==LayoutMode::Training;
    const int scale=big?2:1, width=32*scale, height=36*scale+(big?HOP:0);
    const int lift=big?((running && frame)?0:HOP):0;   // raised on frame 1
    lv_color_t bg=lv_color_hex(BG), fg=lv_color_hex(ink);
    for(int i=0;i<width*height;++i) dinoBuffer[i]=bg;
    for(int y=0;y<36;++y) for(int x=0;x<32;++x) if(hi[y][x])
        for(int sy=0;sy<scale;++sy) for(int sx=0;sx<scale;++sx)
            dinoBuffer[(y*scale+sy+lift)*width+x*scale+sx]=fg;
    lv_obj_invalidate(dinoCanvas);
    lv_label_set_text(dinoMark,sleeping||state==RunState::Stalled?"z":state==RunState::Queued?"...":state==RunState::Error?"!":state==RunState::Completed?"+":"");
}
void buildList(lv_obj_t *screen) {
    header=label(screen,12,8,"",F_LIMIT);
    pageLabel=label(screen,744,10,"",F_SMALL,DIM);
    rect(screen,12,34,796,1,LINE);
    const bool gpuPage=mode==LayoutMode::Gpu;
    const int y0=gpuPage?GPU_Y:LIST_Y, rows=gpuPage?GPU_ROWS:LIST_ROWS;
    // Overview: state mark, name, status, ETA, loss. GPU: VRAM, type, user, command.
    const int xs[2][4]={{30,530,620,720},{12,100,130,290}}, ws[2][4]={{480,80,90,90},{80,20,150,518}};
    for(int i=0;i<LIST_ROWS;++i) {
        for(int c=0;c<4;++c) cells[i][c]=nullptr;
        marks[i]=nullptr;
        if(i>=rows) continue;
        int y=y0+i*LIST_ROW_H;
        if(!gpuPage) marks[i]=rect(screen,12,y+5,10,10,DIM);
        for(int c=0;c<4;++c) {
            cells[i][c]=label(screen,xs[gpuPage][c],y,"",F_SMALL,c==0||(gpuPage&&c==3)?FG:DIM);
            lv_obj_set_size(cells[i][c],ws[gpuPage][c],lv_font_get_line_height(F_SMALL)); lv_label_set_long_mode(cells[i][c],LV_LABEL_LONG_DOT);
        }
    }
    vramFill=vramText=nullptr;
    if(gpuPage) {
        rect(screen,12,44,VRAM_W,14,LINE); vramFill=rect(screen,14,46,1,10,FG);
        vramText=label(screen,VRAM_W+28,40,"",F_SMALL);
    }
}
uint32_t stateInk(const TrainingRun &r,uint32_t now) {
    return r.state==RunState::Error?COLORS[2]:isStale(r,now)?COLORS[1]:r.state==RunState::Queued?DIM:
           r.state==RunState::Completed?FG:COLORS[0];
}
void tickOverview(const Telemetry &s,unsigned pg,uint32_t now) {
    unsigned counts[3]={0,0,0};   // running, queued, finished
    for(size_t i=0;i<s.runCount;++i) {
        const auto &r=s.runs[i];
        ++counts[r.state==RunState::Running||r.state==RunState::Stalled?0:r.state==RunState::Queued?1:2];
    }
    char buf[64];
    snprintf(buf,sizeof(buf),"RUNS   %u active   %u queued   %u finished",counts[0],counts[1],counts[2]);
    setText(header,s.runCount?buf:"RUNS   none");
    for(int i=0;i<LIST_ROWS;++i) {
        size_t idx=pg*LIST_ROWS+i;
        if(idx>=s.runCount) { for(int c=0;c<4;++c) setText(cells[i][c],""); lv_obj_add_flag(marks[i],LV_OBJ_FLAG_HIDDEN); continue; }
        const auto &r=s.runs[idx];
        bool stale=isStale(r,now), live=!stale && r.state==RunState::Running;
        lv_obj_clear_flag(marks[i],LV_OBJ_FLAG_HIDDEN); color(marks[i],stateInk(r,now));
        setText(cells[i][0],r.name);
        snprintf(buf,sizeof(buf),"%d%%",int(std::max(0.f,std::min(1.f,r.progress))*100));
        setText(cells[i][1],r.state==RunState::Error?"ERROR":r.state==RunState::Completed?"DONE":
                r.state==RunState::Queued?"QUEUED":stale?"STALE":r.hasProgress?buf:"--%");
        if(live && r.hasEta) formatDuration(r.etaSeconds,buf,sizeof(buf)); else buf[0]=0;
        setText(cells[i][2],buf);
        if(r.hasLoss) snprintf(buf,sizeof(buf),"%.3f",r.loss); else buf[0]=0;
        setText(cells[i][3],buf);
    }
}
void tickGpu(const Telemetry &s,unsigned pg) {
    char buf[96];
    if(!s.gpuCount) {
        setText(header,"GPU   no data (no nvidia-smi on any machine)"); setText(vramText,""); setWidth(vramFill,1);
        for(int i=0;i<GPU_ROWS;++i) for(int c=0;c<4;++c) setText(cells[i][c],"");
        return;
    }
    const auto &g=s.gpus[pg%s.gpuCount];
    snprintf(buf,sizeof(buf),"%s   %s",g.machine[0]?g.machine:"local",g.name); setText(header,buf);
    float frac=g.hasVram&&g.total>0?std::min(1.f,g.used/g.total):0.f;
    setWidth(vramFill,std::max(1,int((VRAM_W-4)*frac)));
    color(vramFill,frac>=.9f?COLORS[2]:frac>=.7f?COLORS[1]:FG);
    char util[12]="--";
    if(g.hasUtil) snprintf(util,sizeof(util),"%.0f%%",g.util);
    if(g.hasVram) snprintf(buf,sizeof(buf),"%.1f / %.1f GB   GPU %s",g.used,g.total,util); else snprintf(buf,sizeof(buf),"GPU %s",util);
    setText(vramText,buf);
    unsigned shown=0,total=0;
    for(size_t k=0;k<s.procCount;++k) if(s.procs[k].gpu==pg%s.gpuCount) ++total;
    for(size_t k=0;k<s.procCount && shown<GPU_ROWS;++k) {
        const auto &p=s.procs[k];
        if(p.gpu!=pg%s.gpuCount) continue;
        if(shown==GPU_ROWS-1 && total>GPU_ROWS) {   // last row: say how many did not fit
            snprintf(buf,sizeof(buf),"+%u more",total-shown);
            setText(cells[shown][0],""); setText(cells[shown][1],""); setText(cells[shown][2],""); setText(cells[shown][3],buf);
            ++shown; break;
        }
        if(p.hasUsed) snprintf(buf,sizeof(buf),"%.2f GB",p.used); else snprintf(buf,sizeof(buf),"--");
        setText(cells[shown][0],buf);
        buf[0]=p.type; buf[1]=0; setText(cells[shown][1],buf);
        setText(cells[shown][2],p.user); setText(cells[shown][3],p.command);
        ++shown;
    }
    for(unsigned i=shown;i<GPU_ROWS;++i) for(int c=0;c<4;++c) setText(cells[i][c],"");
}
void build(const Telemetry &s,uint32_t now) {
    auto *screen=lv_scr_act(); lv_obj_clean(screen);
    lv_obj_set_style_bg_color(screen,lv_color_hex(BG),0); lv_obj_clear_flag(screen,LV_OBJ_FLAG_SCROLLABLE);
    memset(limitText,0,sizeof(limitText));
    page %= std::max(1u,uiPageCount(s));
    if(listMode(mode)) {
        visibleRows=0; buildList(screen);
        contentSig=contentSignature(s); slowAt=now-SLOW_MS;
        return;
    }
    unsigned rowCount=rowsFor(mode);
    int rowHeight=mode==LayoutMode::Training?60:mode==LayoutMode::SleepingFooter?56:58;
    unsigned start=(page%sessionPages(s))*rowCount;
    visibleRows=std::min(rowCount,unsigned(s.sessionCount>start?s.sessionCount-start:0));
    const int lineH=lv_font_get_line_height(F_TITLE);
    for (unsigned i=0;i<visibleRows;++i) {
        const auto &session=s.sessions[start+i]; int y=i*rowHeight+(rowHeight-lineH)/2;
        char prefix[32]; snprintf(prefix,sizeof(prefix),"%s (%s)",session.provider,session.profile);
        label(screen,12,y,prefix,F_TITLE);
        // Titles are static: truncated with an ellipsis, never scrolled.
        // A long label ("Claude (tower)") pushes the title right instead of overlapping it.
        int titleX=std::max(TITLE_X,12+int(lv_txt_get_width(prefix,strlen(prefix),F_TITLE,0,LV_TEXT_FLAG_NONE))+16);
        titles[i]=label(screen,titleX,y,session.title,F_TITLE);
        lv_obj_set_size(titles[i],TITLE_W-(titleX-TITLE_X),lineH); lv_label_set_long_mode(titles[i],LV_LABEL_LONG_DOT);
        auto *housing=rect(screen,780,i*rowHeight+(rowHeight-46)/2,24,46,LINE);
        for (int j=0;j<3;++j) lights[i][j]=rect(housing,6,5+j*13,12,10,DIM);
        lightState[i]=-1;
        if (i+1<visibleRows) rect(screen,12,i*rowHeight+rowHeight-1,748,1,LINE);
    }
    if (!s.sessionCount) label(screen,20,60,s.linked?"no sessions":"waiting for host...",F_MAIN,DIM);
    pageLabel=label(screen,744,mode==LayoutMode::Training?176:mode==LayoutMode::SleepingFooter?290:298,"",F_SMALL,DIM);
    dinoKey=~0u; sparkRun=-1; spark=sparkVal=nullptr;
    if (mode==LayoutMode::FullSessions) {
        rect(screen,12,292,796,1,LINE);
        buildLimits(screen,12,296,false);
    } else if (mode==LayoutMode::SleepingFooter) {
        rect(screen,12,282,796,2,LINE);
        dinoCanvas=lv_canvas_create(screen);
        lv_canvas_set_buffer(dinoCanvas,dinoBuffer,32,36,LV_IMG_CF_TRUE_COLOR);
        lv_obj_set_pos(dinoCanvas,16,284);
        dinoMark=label(screen,50,284,"",F_SMALL,DIM);
        buildLimits(screen,90,292,false);
    } else {
        rect(screen,12,199,796,2,LINE);
        dinoCanvas=lv_canvas_create(screen);
        lv_canvas_set_buffer(dinoCanvas,dinoBuffer,64,72+HOP,LV_IMG_CF_TRUE_COLOR);
        lv_obj_set_pos(dinoCanvas,20,216);
        dinoMark=label(screen,86,212,"",F_SMALL,DIM);
        runName=label(screen,110,204,"",F_SMALL,DIM);
        lv_obj_set_size(runName,480,lv_font_get_line_height(F_SMALL)); lv_label_set_long_mode(runName,LV_LABEL_LONG_DOT);
        rect(screen,110,230,BAR_W,16,LINE); bar=rect(screen,112,232,1,12,FG);
        percent=label(screen,110+BAR_W+14,222,"",F_MAIN);
        metrics=label(screen,110,254,"",F_MAIN);
        gpu=label(screen,110,292,"",F_SMALL,DIM);
        spark=lv_line_create(screen); lv_obj_set_pos(spark,396,260);
        lv_obj_set_style_line_width(spark,2,0); lv_obj_set_style_line_color(spark,lv_color_hex(FG),0);
        lv_obj_set_style_line_rounded(spark,false,0);
        sparkVal=lv_line_create(screen); lv_obj_set_pos(sparkVal,396,260);
        lv_obj_set_style_line_width(sparkVal,2,0); lv_obj_set_style_line_color(sparkVal,lv_color_hex(VAL),0);
        lv_obj_set_style_line_rounded(sparkVal,false,0);
        lossLabel=label(screen,396,292,"",F_SMALL,FG);
        valLabel=label(screen,486,292,"",F_SMALL,VAL);
        accLabel=label(screen,396,204,"",F_SMALL,VAL);
        rect(screen,596,208,1,104,LINE);
        buildLimits(screen,PANEL_X,206,true);
    }
    contentSig=contentSignature(s);
    slowAt=now-SLOW_MS;   // force a full data refresh on the next tick
}
}
unsigned uiPage(){return page+1;}
unsigned uiPageCount(const Telemetry &s){
    if(mode==LayoutMode::Overview) return std::max(1u,(unsigned(s.runCount)+LIST_ROWS-1)/LIST_ROWS);
    if(mode==LayoutMode::Gpu) return std::max(1u,unsigned(s.gpuCount));
    unsigned pages=sessionPages(s);
    return mode==LayoutMode::Training?std::max(pages,unsigned(s.runCount)):pages;
}
unsigned uiRun(const Telemetry &s){return s.runCount?unsigned(page%s.runCount):0;}
bool uiForced(){return forced;}
LayoutMode uiMode(){return mode;}
static LayoutMode autoMode(const Telemetry &s){return s.runCount?LayoutMode::Training:LayoutMode::SleepingFooter;}
void uiInit(const Telemetry &s,uint32_t now){forced=false;mode=autoMode(s);page=0;build(s,now);uiTick(s,now);}
void uiNextPage(const Telemetry &s,uint32_t now){page=(page+1)%uiPageCount(s);build(s,now);uiTick(s,now);}
void uiSetMode(LayoutMode m,const Telemetry &s,uint32_t now){forced=true;mode=m;page=0;build(s,now);uiTick(s,now);}
void uiAuto(const Telemetry &s,uint32_t now){forced=false;mode=autoMode(s);page=0;build(s,now);uiTick(s,now);}
void uiTick(const Telemetry &s,uint32_t now) {
    if(!forced && mode!=autoMode(s)) {mode=autoMode(s);page=0;build(s,now);}
    if(mode==LayoutMode::Training || mode==LayoutMode::SleepingFooter) drawDino(s,now);   // cheap: redraws only when a step changes
    if(uint32_t(now-slowAt)<SLOW_MS) return;
    slowAt=now;
    if(contentSignature(s)!=contentSig) { build(s,now); }   // sessions/runs changed: rebuild once
    unsigned rowCount=rowsFor(mode);
    unsigned start=(page%sessionPages(s))*rowCount;
    for(unsigned i=0;i<visibleRows;++i) {
        int status=int(s.sessions[start+i].status);
        if(status==lightState[i]) continue;
        lightState[i]=status;
        // Red at top, amber center, green bottom: position reinforces color.
        for(int j=0;j<3;++j) color(lights[i][j],j==2-status?COLORS[status]:0x243020);
    }
    char buf[100];
    snprintf(buf,sizeof(buf),"%u/%u",uiPage(),uiPageCount(s)); setText(pageLabel,uiPageCount(s)>1?buf:"");
    updateLimits(s);
    if(mode==LayoutMode::Overview) { tickOverview(s,page%uiPageCount(s),now); return; }
    if(mode==LayoutMode::Gpu) { tickGpu(s,page%uiPageCount(s)); return; }
    if(mode!=LayoutMode::Training) return;
    const unsigned runIdx=uiRun(s);
    const auto &r=s.runs[runIdx];
    bool stale=isStale(r,now);
    const bool queued=r.state==RunState::Queued;
    uint32_t ink=r.state==RunState::Error?COLORS[2]:stale?COLORS[1]:queued?DIM:FG;
    if(s.runCount>1) snprintf(buf,sizeof(buf),"%u/%u %s",runIdx+1,unsigned(s.runCount),r.name); else snprintf(buf,sizeof(buf),"%s",r.name);
    setText(runName,buf);
    color(bar,ink);
    float progress=std::max(0.f,std::min(1.f,r.progress));
    // Unknown progress shows an empty bar and "--%": no indeterminate animation.
    setWidth(bar,r.hasProgress?std::max(1,int((BAR_W-4)*progress)):1);
    snprintf(buf,sizeof(buf),"%d%%",int(progress*100));
    setText(percent,r.state==RunState::Error?"ERROR":r.state==RunState::Completed?"DONE":queued?"QUEUED":stale?"STALE":r.hasProgress?buf:"--%");
    lv_obj_set_style_text_color(percent,lv_color_hex(ink),0);
    if(queued) {
        // A planned run has no metrics: show its place in the queue and clear everything else.
        unsigned position=0;
        for(unsigned i=0;i<=runIdx;++i) if(s.runs[i].state==RunState::Queued) ++position;
        if(position==1) snprintf(buf,sizeof(buf),"next up"); else snprintf(buf,sizeof(buf),"#%u in queue",position);
        setText(metrics,buf); setText(gpu,""); setText(lossLabel,""); setText(valLabel,""); setText(accLabel,"");
        lv_obj_add_flag(spark,LV_OBJ_FLAG_HIDDEN); lv_obj_add_flag(sparkVal,LV_OBJ_FLAG_HIDDEN); sparkRun=-1;
        return;
    }
    char rate[20]="--",eta[20]="--",loss[20]="--",util[20]="--",vram[32]="";
    bool live=!stale && r.state==RunState::Running;
    if(r.hasRate && live) snprintf(rate,sizeof(rate),"%.1f",r.rate);
    if(r.hasEta && live) formatDuration(r.etaSeconds,eta,sizeof(eta));
    if(r.hasLoss) snprintf(loss,sizeof(loss),"%.3f",r.loss);
    if(r.hasGpu) snprintf(util,sizeof(util),"%.0f%%",r.gpu);
    if(r.hasVram) snprintf(vram,sizeof(vram),"   VRAM %.1f/%.0fG",r.vramUsed,r.vramTotal);
    snprintf(buf,sizeof(buf),"%s/s   ETA %s",rate,eta); setText(metrics,buf);
    if(r.hasGpu) snprintf(buf,sizeof(buf),"GPU %s%s",util,vram); else buf[0]=0;   // CPU-only runs: no GPU line
    setText(gpu,buf);
    snprintf(buf,sizeof(buf),"loss %s",r.hasLoss?(loss[0]=='0'?loss+1:loss):"--"); setText(lossLabel,buf);
    if(r.val.count) { snprintf(buf,sizeof(buf),"val %.3f",r.val.v[r.val.count-1]); if(buf[4]=='0') memmove(buf+4,buf+5,strlen(buf+5)+1); }
    else buf[0]=0;
    setText(valLabel,buf);
    if(r.hasAcc) snprintf(buf,sizeof(buf),"val acc %.1f%%",r.acc); else buf[0]=0;
    setText(accLabel,buf);
    // Loss plot: train and validation share one scale and one x axis. Redrawn only when something changed.
    if(!r.hasLoss || r.train.count<2) { lv_obj_add_flag(spark,LV_OBJ_FLAG_HIDDEN); lv_obj_add_flag(sparkVal,LV_OBJ_FLAG_HIDDEN); sparkRun=-1; return; }
    float last=r.train.v[r.train.count-1], valLast=r.val.count?r.val.v[r.val.count-1]:-1.f;
    if(sparkRun==int(runIdx) && sparkLast==last && sparkCount==r.train.count && sparkValLast==valLast && sparkValCount==r.val.count) return;
    sparkRun=int(runIdx); sparkLast=last; sparkCount=r.train.count; sparkValLast=valLast; sparkValCount=r.val.count;
    float lo=r.train.v[0],hi=lo;
    for(unsigned k=0;k<r.train.count;++k) { lo=std::min(lo,r.train.v[k]); hi=std::max(hi,r.train.v[k]); }
    for(unsigned k=0;k<r.val.count;++k) { lo=std::min(lo,r.val.v[k]); hi=std::max(hi,r.val.v[k]); }
    float range=std::max(hi-lo,1e-6f);
    auto plot=[&](lv_obj_t *line,const LossSeries &series,lv_point_t *points) {
        if(series.count<2) { lv_obj_add_flag(line,LV_OBJ_FLAG_HIDDEN); return; }
        for(unsigned k=0;k<series.count;++k) {
            points[k].x=int(series.x[k]*(SPARK_W-1)/(LossHistory-1));
            points[k].y=(SPARK_H-1)-int((series.v[k]-lo)/range*(SPARK_H-1));
        }
        lv_obj_clear_flag(line,LV_OBJ_FLAG_HIDDEN);
        lv_line_set_points(line,points,series.count);
    };
    plot(spark,r.train,sparkPoints);
    plot(sparkVal,r.val,sparkValPoints);
}

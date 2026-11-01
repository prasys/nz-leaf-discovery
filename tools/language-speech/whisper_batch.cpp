// Local draft transcription of generated GID WAVs, using installed whisper.cpp.
// Never loads or executes firmware. Build instructions are in findings 14.
#include <whisper.h>
#include <ggml-backend.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

static uint32_t le(const std::vector<unsigned char>& b, size_t p, size_t n) {
    if (p+n > b.size()) throw std::runtime_error("truncated WAV");
    uint32_t x = 0;
    for (size_t i = 0; i < n; ++i) x |= uint32_t(b[p+i]) << (8*i);
    return x;
}
static std::vector<float> read_wav(const std::filesystem::path& path, float& rms) {
    std::ifstream in(path, std::ios::binary);
    std::vector<unsigned char> b((std::istreambuf_iterator<char>(in)), {});
    if (b.size()<44 || std::string(b.begin(),b.begin()+4)!="RIFF" ||
        std::string(b.begin()+8,b.begin()+12)!="WAVE") throw std::runtime_error("invalid WAV");
    uint32_t rate=0; size_t data=0, length=0;
    for (size_t p=12; p+8<=b.size();) {
        std::string kind(b.begin()+p,b.begin()+p+4);
        uint32_t n=le(b,p+4,4);
        if (n>b.size()-p-8) throw std::runtime_error("invalid WAV chunk");
        if (kind=="fmt ") {
            if (n<16 || le(b,p+8,2)!=1 || le(b,p+10,2)!=1 || le(b,p+22,2)!=16)
                throw std::runtime_error("need mono s16 WAV");
            rate=le(b,p+12,4);
        } else if (kind=="data") { data=p+8; length=n/2; }
        p += 8 + n + (n&1);
    }
    if (!rate || !data || !length || rate>192000) throw std::runtime_error("missing WAV data/rate");
    std::vector<float> raw(length);
    double sum=0;
    for (size_t i=0; i<length; ++i) {
        int16_t s=static_cast<int16_t>(le(b,data+2*i,2));
        raw[i]=s/32768.0f; sum+=double(s)*s;
    }
    rms=std::sqrt(sum/length);
    std::vector<float> samples(size_t(double(length)*16000/rate));
    for (size_t i=0; i<samples.size(); ++i) {
        double p=double(i)*rate/16000; size_t left=size_t(p);
        double f=p-left;
        samples[i]=float(raw[left]*(1-f)+raw[std::min(left+1,length-1)]*f);
    }
    return samples;
}
int main(int argc, char** argv) {
    if (argc!=6) { std::cerr<<"model decoded-dir output.tsv start end; set VOICE_TRANSLATE=1 for English\n"; return 2; }
    try {
        const char* home=std::getenv("HOME");
        if (!home) throw std::runtime_error("HOME is unset");
        std::string root=(std::filesystem::path(home)/"nissan/work/language-speech").string()+"/";
        for (int i=1; i<=3; ++i) {
            std::string path=std::filesystem::weakly_canonical(argv[i]).string();
            if (path.compare(0,root.size(),root)!=0) throw std::runtime_error("artifacts must be under ~/nissan/work/language-speech/");
        }
        if (std::filesystem::exists(argv[3])) throw std::runtime_error("refusing to overwrite transcript");
        int first=std::stoi(argv[4]), last=std::stoi(argv[5]);
        if (first<0 || last<first || last>2071) throw std::runtime_error("invalid public clip range");
        std::set<int> selected;
        if (const char* ids=std::getenv("VOICE_REVIEW_IDS")) {
            std::istringstream input(ids); std::string item;
            while (std::getline(input,item,',')) {
                size_t used; int id=std::stoi(item,&used);
                if (used!=item.size() || id<0 || id>=2071) throw std::runtime_error("invalid review clip");
                selected.insert(id);
            }
            if (selected.empty()) throw std::runtime_error("empty review clip list");
        }
        if (const char* backend=std::getenv("VOICE_GGML_CPU")) {
            if (!ggml_backend_load(backend)) throw std::runtime_error("CPU backend load failed");
        } else ggml_backend_load_all();
        if (const char* backend=std::getenv("VOICE_GGML_BLAS")) {
            if (!ggml_backend_load(backend)) throw std::runtime_error("BLAS backend load failed");
        }
        auto cp=whisper_context_default_params(); cp.use_gpu=false;
        auto* ctx=whisper_init_from_file_with_params(argv[1],cp);
        if (!ctx) throw std::runtime_error("model load failed");
        std::ofstream out(argv[3]);
        if (!out) throw std::runtime_error("cannot create transcript");
        out<<"clip\ttext\tmean_token_probability\ttokens\tlimit\n";
        for (int id=first; id<last; ++id) {
            if (!selected.empty() && !selected.count(id)) continue;
            char name[32]; snprintf(name,sizeof(name),"clip%04d.wav",id);
            auto path=std::filesystem::path(argv[2])/name;
            if (!std::filesystem::exists(path)) continue;
            float rms; auto samples=read_wav(path,rms);
            std::string text; float prob=0; int tokens=0;
            double duration=samples.size()/16000.0;
            auto p=whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
            p.n_threads=3; p.language="ja"; p.translate=std::getenv("VOICE_TRANSLATE")!=nullptr;
            p.no_context=true; p.single_segment=true; p.no_timestamps=true;
            p.print_progress=false; p.print_realtime=false; p.print_timestamps=false;
            p.temperature=0; p.temperature_inc=0;
            p.audio_ctx=std::min(1500,std::max(256,int(std::ceil((duration*50+32)/64))*64));
            if (std::getenv("VOICE_FULL_CONTEXT")) p.audio_ctx=0;
            p.max_tokens=std::min(192,std::max(16,int(duration*12)+8));
            if (rms>=10) {
                if (whisper_full(ctx,p,samples.data(),int(samples.size()))!=0)
                    throw std::runtime_error("inference failed");
                for (int j=0; j<whisper_full_n_segments(ctx); ++j) {
                    text+=whisper_full_get_segment_text(ctx,j);
                    for (int k=0; k<whisper_full_n_tokens(ctx,j); ++k) {
                        prob+=whisper_full_get_token_p(ctx,j,k); ++tokens;
                    }
                }
            }
            for (char& c:text) if (c=='\t' || c=='\n' || c=='\r') c=' ';
            out<<id<<'\t'<<text<<'\t'<<(tokens?prob/tokens:0)<<'\t'<<tokens<<'\t'<<p.max_tokens<<'\n';
            out.flush();
            if (id%100==0) std::cerr<<"completed clip "<<id<<'\n';
        }
        whisper_free(ctx);
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}

# Ka-band RF 자동설계 프로그램 개요

## 1. 목적

**위성통신용 RF 부품 자료 수집부터 호환성 검사, 송수신 체인 구성, 링크 성능 비교까지 지원하는 초기 설계 도구.**

설계 목표: 주파수·연결·출력 조건 아래, 링크 성능·부품 등급·소비전력 기준 최우선 RF 체인 선택. 제조사별 데이터시트 비교 및 반복 계산 부담 축소.

적용 대상: 지상 단말(Terminal)·위성 탑재체(Payload). 설정 대역: 상향링크 27.5–31.0 GHz, 하향링크 17.7–21.2 GHz. Flask 백엔드와 Vue.js 웹 화면 제공.

## 2. 주요 기능

| 기능 | 주요 내용 |
|---|---|
| 제조사 자료 수집 | 공식 제품 페이지·카탈로그 탐색, 데이터시트 PDF 다운로드 |
| 사양 자동 추출 | PDF 텍스트·OCR 기반 주파수, 이득, 출력, 잡음지수 등 추출 |
| 부품 데이터 관리 | CSV 저장·가져오기·다운로드, 수동 수정, 기준 Excel 자료 병합 |
| 요구조건 설정 | 적용 대상, 송수신 방향, 주파수, 대역폭, 목표 처리량, 고도·앙각 등 입력 |
| 호환성 검사 | 적용 대상·방향·주파수·대역폭·빔 수 및 부품 간 연결 조건 확인 |
| 부품 조합 생성 | 송신·수신 경로 구성, 부적합 조합 제외, 후보 우선순위 산정 |
| 성능 계산 | 단계별 출력, 유효등방성복사전력(EIRP), 수신 잡음지수(NF), 신호대잡음비(SNR), MCS·처리량 계산 |
| 결과 확인 | Tx 후보 최대 50개 표시·CSV 다운로드, 선택 부품 제품·데이터시트 링크 제공, Rx 최상위 후보 표시 |

처리 흐름: **공식 자료 수집 → 사양 추출·CSV 저장 → 요구조건 검사 → 부품 조합 → 성능 계산·후보 정렬**.

## 3. 부품 조합 방식

| 구분 | 기본 RF 신호 경로 | 필수 부품 |
|---|---|---|
| 송신(Tx) | DAC → Mixer → BFIC → PA → Switch | Mixer·PLL·BFIC·PA |
| 수신(Rx) | Switch → LNA → BFIC → Mixer → ADC | LNA·BFIC·Mixer·PLL |

BFIC: 빔포밍 집적회로, PA: 전력 증폭기, LNA: 저잡음 증폭기. PLL: Mixer에 국부발진(LO) 신호 공급, RF 직렬 경로와 별도 연결. ADC/DAC: 후보 부재 시 생략. Tx Switch: 생략 가능, Rx Switch: 후보 존재 시 포함.

조합 절차:

1. 개별 부품 요구조건 검사 후 FAIL 부품 제외.
2. 부품 종류별 후보 조합 열거, 기본 최대 5,000개 조합 확인.
3. PLL–Mixer LO 주파수·구동 전력 검사, Tx BFIC–PA 구동 가능성 검사.
4. Tx 출력·링크 성능 또는 Rx 이득·잡음지수 계산 후 정렬.

필수 종류 후보 부재 시 조합 생성 불가. 사양 부족 상태(UNKNOWN)는 일부 후보에 유지. Rx RF 체인 이득·NF 계산 불가 조합은 제외.

## 4. 후보 순위 산정 기준

**가중 점수 합산 없이, 상위 기준 동률 시 다음 기준 적용하는 사전식 정렬.**

| 순위 기준 적용 순서 | 송신(Tx) | 수신(Rx) |
|---|---|---|
| 1 | 최종 PASS 후보 우선 | Payload 대상 Space-grade 이외 부품 수 최소화 |
| 2 | Payload 대상 Space-grade 이외 부품 수 최소화 | 전체 잡음지수 최소화 |
| 3 | 링크 마진 최대화 | 전체 이득 최대화 |
| 4 | 목표 대비 처리량 여유 최대화 | 소비전력 최소화 |
| 5 | 소비전력 최소화 | — |
| 6 | 부품 수 최소화 | — |

링크 마진: 목표 처리량 달성에 필요한 최소 SNR 대비 예측 SNR 여유. Terminal 조건에서는 등급 기준 생략. 예를 들어 동일 PASS인 Payload 후보 비교 시 링크 마진보다 우주용 등급 부품 구성 우선.

Tx 최종 WARN·UNKNOWN·FAIL: 모두 비-PASS 그룹으로 묶은 뒤 나머지 기준 적용. PASS 부재 시 최상위 후보 표시, 요구조건 충족 보장 없음. 가격·재고·납기 기준 최적화 미구현.

## 5. 최적화 문제 정의

### 5.1 문제 설정과 구현 수준

설계 문제: **주어진 링크 요구조건 아래, 연결 가능한 RF 부품 조합 중 성능·등급·소비전력 기준 최우선 체인 선택**. 부품 선택: 이산 조합 문제. 출력·잡음·링크 계산: 후보별 성능 평가 함수.

현재 구현: `itertools.product` 기반 조합 열거 → 부적합 후보 제거 → 성능 계산 → 사전식 정렬(lexicographic ordering). 별도 최적화 solver, 명시적 slack 변수, 가중 페널티 최소화 루틴 미사용.

아래 구분 기준:

| 구분 | 설명 |
|---|---|
| 현재 구현 수식화 | 코드 내 필터·계산·정렬 동작의 수학적 표현 |
| 엄격한 설계 정식화 | 사양 완비 전제, 물리적 호환성을 hard constraint로 표현 |
| Slack 기반 확장안 | 목표 미달량 정량화 및 차선 후보 선택 개선용 제안; 현재 미구현 |

### 5.2 결정변수와 평가량

단계 집합 $\mathcal K$, 단계 $k$의 부품 후보 집합 $\mathcal C_k$ 정의.

$$
x_{kj}=\begin{cases}
1 & \text{단계 }k\text{에서 부품 }j\text{ 선택}\\
0 & \text{그 외}
\end{cases}
\qquad(k\in\mathcal K,\ j\in\mathcal C_k)
$$

| 기호 | 의미 | 현재 코드 대응 |
|---|---|---|
| $x$ | 체인 부품 선택 벡터 | 조합 열거 결과 |
| $a_k\ge0$ | 단계별 출력 감소량, dB | 자동 레벨 제어 결과; 독립 최적화 변수 아님 |
| $\ell$ | Mixer 외부 LO 입력 주파수, GHz | 가능한 LO 후보 중 검사 통과값 |
| $R(x)$ | 예측 처리량, Mbps | `throughput_mbps` |
| $M(x)$ | 목표 처리량 기준 SNR 여유, dB | `link_margin_db` |
| $P_{\mathrm{DC}}(x)$ | 선택 부품 소비전력 합, W | `total_power_w` |
| $C(x)$ | Space-grade 이외 부품 수 | Payload 후보 우선순위 |
| $n(x)$ | 선택 부품 수 | Tx 최종 정렬 기준 |
| $NF(x),G(x)$ | 수신 체인 잡음지수·이득, dB | Rx 후보 평가량 |

기본 설계변수: $x$. 사용자 지정 중심주파수·대역폭·안테나 이득·백오프·빔 수 등: 고정 파라미터. MCS: 후보 SNR 기반 후속 선택값.

### 5.3 목적함수: 현재 구현의 사전식 최소화

Tx 후보 집합 $\mathcal E_{\mathrm{Tx}}$: 최초 최대 5,000개 조합 중 개별 부품·부품 간 FAIL 필터 통과 후보. 상태 지시값 $q(x)=0$ if 최종 PASS, 그 외 $q(x)=1$.

$$
\begin{aligned}
\underset{x}{\operatorname{lexmin}}\quad
&\left(q(x),\ I_{\mathrm{Payload}}C(x),\ -M(x),\ -[R(x)-R_{\mathrm{target}}],\ P_{\mathrm{DC}}(x),\ n(x)\right)\\
\text{subject to}\quad
&x\in\mathcal E_{\mathrm{Tx}}.
\end{aligned}
$$

$I_{\mathrm{Payload}}$: Payload 조건에서 1, Terminal 조건에서 0. `lexmin`: 첫 항 최소화 후 동률 후보에만 다음 항 적용. 가중합 방식과 달리 상위 기준 손실을 하위 기준 개선으로 상쇄 불가.

예: Payload·동일 PASS 후보 비교 시 상용등급 부품 수 우선. 더 큰 링크 마진보다 Space-grade 구성 우선 가능. 최종 WARN·UNKNOWN·FAIL 사이 별도 상태 순위 없음: 모두 $q=1$ 처리 후 다음 항 비교.

Rx 목적함수:

$$
\begin{aligned}
\underset{x}{\operatorname{lexmin}}\quad
&\left(I_{\mathrm{Payload}}C(x),\ NF(x),\ -G(x),\ P_{\mathrm{DC}}(x)\right)\\
\text{subject to}\quad
&x\in\mathcal E_{\mathrm{Rx}}.
\end{aligned}
$$

$\mathcal E_{\mathrm{Rx}}$: 개별 부품·LO FAIL 필터 통과 및 RF 체인 이득·NF 계산 가능 후보. 현재 Rx 목적함수에 목표 처리량 항 없음.

누락값 처리: 정의 불가 링크 마진 및 전체 소비전력 미상에 정렬용 대체값 적용. 일부 소비전력만 존재하는 경우 부분 합계 사용. 따라서 목적함수 해석 전 데이터 완전성 확인 필요.

### 5.4 Subject to: 물리적 호환성 hard constraints

다음 수식: 사양 완비 전제의 엄격한 설계 모델. 선택 부품만 해당 제약 적용. 현재 코드와 차이: 표 하단 명시.

**① 단계별 부품 선택**

$$
\sum_{j\in\mathcal C_k}x_{kj}=1\quad(k\in\mathcal K_{\mathrm{required}}),
\qquad
\sum_{j\in\mathcal C_k}x_{kj}\le1\quad(k\in\mathcal K_{\mathrm{optional}}),
\qquad x_{kj}\in\{0,1\}.
$$

필수 단계별 정확히 1개 선택. 생략 허용 단계별 최대 1개 선택. 현재 구현에서는 변환기 후보 존재 시 선택 강제, Rx Switch 후보 존재 시 선택 강제. 선택 가능 단계 집합에 해당 정책 반영 필요.

**② 적용 대상·송수신 방향 및 주파수 범위**

$$
x_{kj}=1\ \Longrightarrow\
\left\{
\begin{aligned}
&A_{kj}=1,\quad D_{kj}=1,\\
&f_{kj}^{\min}\le f_c-\frac{B_{\mathrm{MHz}}}{2000},\\
&f_{kj}^{\max}\ge f_c+\frac{B_{\mathrm{MHz}}}{2000},\\
&B_{kj}^{\mathrm{GHz}}\ge\frac{B_{\mathrm{MHz}}}{1000}.
\end{aligned}
\right.
$$

$A_{kj},D_{kj}$: 적용 대상·방향 적합 여부. 주파수 단위 GHz, 채널 대역폭 $B_{\mathrm{MHz}}$ 단위 MHz. 대역폭 조건: BFIC·Mixer·변환기 대상. ADC/DAC 주파수 조건: 지정 IF 기준. PLL 주파수 조건: 다음 LO 제약으로 검사.

BFIC 빔 수 조건:

$$
x_{kj}=1\ \Longrightarrow\ N_{kj}^{\mathrm{beam}}\ge N_{\mathrm{req}}^{\mathrm{beam}}.
$$

**③ PLL–Mixer 연결 가능성**

Mixer 내부 LO 배율 $\mu$, 외부 LO 입력 $\ell$ 정의.

$$
\begin{aligned}
\ell&\in\left\{\frac{|f_{\mathrm{RF}}-f_{\mathrm{IF}}|}{\mu},
\frac{f_{\mathrm{RF}}+f_{\mathrm{IF}}}{\mu}\right\},\\
\max(f_{\mathrm{PLL}}^{\min},f_{\mathrm{Mixer,LO}}^{\min})
&\le\ell\le
\min(f_{\mathrm{PLL}}^{\max},f_{\mathrm{Mixer,LO}}^{\max}),\\
P_{\mathrm{PLL,out}}-L_{\mathrm{routing}}
&\ge P_{\mathrm{Mixer,LO}}^{\min}.
\end{aligned}
$$

의미: 주파수 변환 관계, 공통 LO 대역, 최소 구동 전력 동시 충족. 현재 코드: LO 최대 구동 전력 제한 미검사.

**④ BFIC–PA 구동 및 단계별 출력 한계**

$$
\begin{aligned}
P_{\mathrm{PA,in,req}}&=OP_{1\mathrm{dB,PA}}-OBO-G_{\mathrm{PA}},\\
OP_{1\mathrm{dB,BFIC}}&\ge P_{\mathrm{PA,in,req}},\\
P_{k,\mathrm{out}}&=P_{k,\mathrm{in}}+G_k-a_k,\quad a_k\ge0,\\
P_{k,\mathrm{out}}&\le P_{k,\mathrm{allow}},\quad
P_{k+1,\mathrm{in}}=P_{k,\mathrm{out}}.
\end{aligned}
$$

$OP_{1\mathrm{dB}}$: 출력 1 dB 압축점, $OBO$: 출력 백오프. 전력 단위 dBm, 이득·백오프·감쇠 단위 dB.

$P_{k,\mathrm{allow}}$: PA P1dB−백오프, 일반 증폭 단계 P1dB, Switch 허용 전력 등. 현재 자동 레벨 제어: 상한 충족용 출력 조절 가정. $a_k$는 제어량이며 제약 위반 허용량과 구분. 실제 감쇠기 범위·해상도·추가 손실 제약 미구현.

| 조건 | 현재 구현에서의 처리 |
|---|---|
| 개별 부품 적합성 | 확인 가능한 위반은 FAIL 제외; 사양 누락은 UNKNOWN 유지 |
| PLL–Mixer·BFIC–PA | FAIL 조합 제외; UNKNOWN 조합 유지 |
| 단계별 출력 상한 | 알려진 상한 기준 자동 조절; 한계 미상은 UNKNOWN |
| Rx 이득·NF | RF 체인 계산 불가 조합 제외 |
| 목표 처리량 | 미달 후보 보존; 링크 결과 FAIL 및 순위에 반영 |
| 최대 소비전력·최대 NF | 사용자 지정 hard constraint 미구현; 정렬 지표로 사용 |

따라서 현재 후보 집합은 엄격한 의미의 ‘모든 제약 충족 집합’과 불일치. 정보 부족 후보 포함 가능. UNKNOWN 처리 정책 강화 및 개별 검사 결과 최종 상태 통합 필요.

### 5.5 성능 평가 함수: 목적함수와 제약의 연결

Tx 부품 선택 → 복합 Peak EIRP → 빔별 백오프 EIRP → 보어사이트·최대 슬랜트 SNR → MCS → 최대·최소 처리량 경로로 계산한다.

| 기호 | 엔진 필드 | 계산·입력 |
|---|---|---|
| A | `center_freq_ghz` | 중심 주파수(GHz) 입력 |
| B | `channel_bw_mhz` | 채널 대역폭(MHz) 입력 |
| C | `control_overhead` | 제어 오버헤드 비율 입력 |
| D | `boresight_range_km` | `altitude_km` 입력값 |
| E | `elevation_deg` | 고도각(도) 입력 |
| F | `slant_range_km` | $\sqrt{(R_E+D)^2-(R_E\cos E)^2}-R_E\sin E$ |
| G | `num_beams` | 빔 수 입력 |
| H | `peak_eirp_dbw` | 복합 Peak EIRP(dBW) 입력 또는 Tx 체인에서 산출 |
| I | `peak_eirp_per_beam_dbw` | $H-10\log_{10}G$ |
| J | `output_backoff_db` | 출력 백오프(dB) 입력 |
| K | `composite_eirp_backoff_dbw` | $H-J$ |
| L | `linear_eirp_per_beam_dbw` | $I-J$ |
| M | `boresight_path_loss_db` | $92.45+20\log_{10}A+20\log_{10}D$ |
| N | `max_slant_path_loss_db` | $92.45+20\log_{10}A+20\log_{10}F$ |
| O·P·Q | 대기·신틸레이션·강우 손실 | `atmospheric_loss_db`, `scintillation_loss_db`, `rain_loss_db` 입력 |
| R | `gt_db_per_k` | $V-10\log_{10}S-W$ |
| S | `system_noise_temperature_k` | $290(10^{U/10}-1)+T$ |
| T·U·V·W | 수신 입력 | 천공 온도, NF, coherent gain, BF error |
| X | `eis_dbm` | $-174+10\log_{10}(B\times10^6)+U-V$ |
| Y | `boresight_noise_snr_db` | $L+30-M-O-P-Q-X$ |
| Z | `boresight_nonlinear_snr_db` | `nonlinear_snr_db` 입력 |
| AA | `boresight_total_snr_db` | $-10\log_{10}(10^{-Y/10}+10^{-Z/10})$ |
| AB | `max_slant_noise_snr_db` | $L+30-N-O-P-Q-X$ |
| AC | `max_slant_nonlinear_snr_db` | 최대 슬랜트 비선형 SNR 입력 |
| AD | `max_slant_total_snr_db` | $-10\log_{10}(10^{-AB/10}+10^{-AC/10})$ |
| AE·AF | `max_mcs`, `min_mcs` | AA·AD가 속하는 MCS 구간의 최대 스펙트럼 효율 선택 |
| AG·AH | `max_throughput_mbps`, `min_throughput_mbps` | $\eta_m B(1-C)\phi$ |

$R_E=6371$ km이며 $\phi$(`fill_factor`)는 기준 엑셀 `MCS!I42`의 자원 이용 보정계수 $\eta$에 해당한다. 기준값은 `0.88704`이고 사용자가 변경할 수 있다.

$$
\phi=\frac{N_{\mathrm{PRB}}N_{\mathrm{subcarrier/PRB}}N_{\mathrm{symbol/slot}}N_{\mathrm{slot/s}}}
{B_{\mathrm{reference,MHz}}\times10^6}.
$$

$$
\begin{aligned}
L(x)&=H(x)-10\log_{10}N_{\mathrm{beam}}-OBO,\\
\gamma_{n,\max}(x)&=L(x)+30-L_{\mathrm{FSPL,max}}-L_{\mathrm{env}}
-\left[-174+10\log_{10}B_{\mathrm{Hz}}+NF_{\mathrm{Rx}}-G_{\mathrm{Rx}}\right],\\
\gamma_{\max}(x)&=-10\log_{10}\left(10^{-\gamma_{n,\max}(x)/10}+10^{-\gamma_{\mathrm{NL,max}}/10}\right),\\
R_{\min}(x)&=\eta_{m(\gamma_{\max}(x))}B_{\mathrm{MHz}}(1-\alpha)\phi,\\
M(x)&=\gamma_{\max}(x)-\gamma_{\mathrm{req}}.
\end{aligned}
$$

$L_{\mathrm{env}}$: 대기·강우·신틸레이션 손실 합. $\alpha$: 제어 오버헤드, $\phi$: 자원 이용 보정계수. $\eta_{m(\gamma(x))}$: SNR 기반 선택 MCS의 스펙트럼 효율. $\gamma_{\mathrm{req}}$: 목표 처리량 달성 가능한 MCS 중 최소 요구 SNR. 해당 MCS 부재 시 $M(x)$ 정의 불가.

EIRP 단위 dBW, 안테나 입력 전력 단위 dBm, SNR 단위 dB, 처리량 단위 Mbps. `throughput_mbps`, `snr_total_db`, `mcs`, `fspl_db`는 기존 API 호환을 위해 각각 보수적인 최대 슬랜트 값 AH, AD, AF, N을 유지한다. 현재 Tx 평가의 $NF_{\mathrm{Rx}}$는 사용자 입력값이며 Rx 후보 결과와 자동 연동되지 않는다.

Rx 부품 선택 → Friis 잡음계수 → 잡음지수 평가:

$$
F(x)=F_1(x)+\sum_{k=2}^{K}
\frac{F_k(x)-1}{\prod_{i=1}^{k-1}g_i(x)},
\qquad NF(x)=10\log_{10}F(x).
$$

$F_k$: 선형 잡음계수, $g_i$: 선형 전력 이득. 계산 범위: Switch·LNA·BFIC·Mixer. 앞단 저잡음·고이득 부품 선택 효과를 $NF(x)$ 최소화 목적에 반영.

### 5.6 Slack variables: 여유와 목표 미달량

**현재 코드: 명시적 slack 변수 미사용.** `throughput_margin_mbps`, `link_margin_db`, 구동 전력 margin 등 사후 계산값 사용. 아래 정식화: 해당 여유의 해석 및 최적화 확장안.

일반 hard constraint $g(x)\le0$의 slack 표현:

$$
g(x)+s=0,\qquad s\ge0.
$$

$s$: 제약 충족 후 남은 여유. 제약 위반 허용 기능 없음. 예를 들어 목표 처리량을 hard constraint로 설정할 경우:

$$
R(x)\ge R_{\mathrm{target}}
\ \Longleftrightarrow\
R(x)-s_R=R_{\mathrm{target}},\qquad s_R\ge0.
$$

반면 달성 불가능한 목표까지 비교하려면 **부족량 변수** $\xi_R\ge0$ 도입:

$$
R(x)+\xi_R\ge R_{\mathrm{target}},\qquad \xi_R\ge0.
$$

$\xi_R$ 최소화 시 $\xi_R^*=\max(0,R_{\mathrm{target}}-R(x))$. 흔히 soft-constraint slack으로 지칭하지만, 본 문서에서는 충족 여유 $s$와 위반 허용량 $\xi$ 구분.

| 요구조건 | 엄격한 조건 | Soft constraint 확장 | 위반량 단위 |
|---|---|---|---|
| 최소 처리량 | $R(x)\ge R_{\mathrm{target}}$ | $R(x)+\xi_R\ge R_{\mathrm{target}}$ | Mbps |
| 최소 링크 마진 | $M(x)\ge M_{\mathrm{req}}$ | $M(x)+\xi_M\ge M_{\mathrm{req}}$ | dB |
| 최대 소비전력 | $P_{\mathrm{DC}}(x)\le P_{\max}$ | $P_{\mathrm{DC}}(x)\le P_{\max}+\xi_P$ | W |
| 최대 수신 NF | $NF(x)\le NF_{\max}$ | $NF(x)\le NF_{\max}+\xi_{NF}$ | dB |

$M_{\mathrm{req}},P_{\max},NF_{\max}$: 확장안 신규 설계 목표. 물리적 연결·동작 불가 조건은 hard constraint 유지. 목표 소비전력 완화와 절대 전원·열 한계 완화 구분 필요.

수치 예: 목표 40 Mbps, 후보 A 38 Mbps, 후보 B 30 Mbps. 현재 링크 판정: 둘 다 FAIL. 부족량 표현: $\xi_R(A)=2$, $\xi_R(B)=10$ Mbps. 부족량 우선 최소화 시 후보 A 우선. 기존 코드: PASS 여부 이후 등급·링크 마진 우선순위 적용으로 동일 선택 보장 없음.

### 5.7 Slack 기반 목적함수 확장안

물리적 제약 충족 집합 $\mathcal H$ 정의. Tx 기준 우선순위: **목표 미달량 최소화 → 등급·마진·전력·부품 수 개선**.

$$
\begin{aligned}
\underset{x,\xi_R,\xi_M,\xi_P}{\operatorname{lexmin}}\quad
&\left(V(\xi),\ I_{\mathrm{Payload}}C(x),\ -M(x),\ P_{\mathrm{DC}}(x),\ n(x)\right)\\
\text{subject to}\quad
&x\in\mathcal H,\\
&R(x)+\xi_R\ge R_{\mathrm{target}},\\
&M(x)+\xi_M\ge M_{\mathrm{req}},\\
&P_{\mathrm{DC}}(x)\le P_{\max}+\xi_P,\\
&\xi_R,\xi_M,\xi_P\ge0,\\[2pt]
V(\xi)=\quad
&w_R\frac{\xi_R}{R_0}
+w_M\frac{\xi_M}{M_0}
+w_P\frac{\xi_P}{P_0}.
\end{aligned}
$$

$R_0,M_0,P_0>0$: 단위 정규화 기준값. $w_R,w_M,w_P>0$: 목표 미달 허용 정책. 서로 다른 단위의 부족량 직접 합산 방지. $V=0$: 모든 soft 목표 충족, $V>0$: 물리적 호환성 확보 상태의 목표 미달 후보.

처리량·링크 마진: 서로 연관된 지표. 두 항 동시 사용 시 중복 페널티 여부 검토 필요. 처리량만 우선할 경우 마진 soft 항 제거 가능. 목표 달성 가능한 MCS 부재 시 $M$ 관련 항 제외 또는 목표 자체의 달성 불가능 상태 별도 보고. 소비전력 누락 후보는 완전한 전력 제약 검증 불가로 별도 분류 필요.

Rx 확장: 처리량 대신 $NF(x)\le NF_{\max}+\xi_{NF}$ 및 NF 부족량 페널티 적용 가능. 송수신 공동 최적화 시 선택 Rx NF를 Tx 링크 평가 함수에 연결하는 추가 구현 필요.

구현 방향: 기존 열거 후보마다 $\xi$ 계산 후 정렬 기준 확장 가능. Solver 도입 전에도 적용 가능. 단, 5,000개 탐색 한도 유지 시 결과 보장 범위는 탐색 완료 후보 집합 내부로 제한.

## 6. 장점

| 장점 | 기대 효과 |
|---|---|
| 자료 수집·계산 흐름 통합 | 제조사별 검색, 사양 정리, 반복 계산 작업 감소 |
| 동일 요구조건 기반 비교 | 부품 조합별 출력·잡음·처리량 비교 기준 일관성 확보 |
| 판정 근거 확인 | PASS·WARN·FAIL·UNKNOWN 및 상세 메시지로 부적합 원인 파악 |
| 추출 근거 기록 | 자동 수집 결과의 출처·페이지·원문 근거 확인 지원 |
| 수동 보정·재활용 | CSV 편집·가져오기, 기존 PDF 재처리로 자료 재사용 가능 |
| 초기 후보 압축 | LO 연결·출력 구동 불가 조합 사전 제외, 평가 대상 축소 |

## 7. 단점 및 한계

| 항목 | 한계·발생 조건 | 영향·보완 방향 |
|---|---|---|
| 웹 크롤링 유지보수 | 제품 링크 경로, HTML 구조, 데이터시트 버튼 문구 변경 시 탐색 실패 가능 | 사이트별 추출 규칙 수정 필요; 작은 변경도 의존 요소 변경 시 영향 |
| 다운로드 접근성 | 자동 요청 차단(HTTP 429), 비공개·NDA 자료, 브라우저 실행 환경 의존 | 수집 누락 가능; 공개 자료·직접 확보 PDF·수동 입력 보완 |
| 사양 추출 정확도 | PDF 표 구조·표기 차이, OCR 오인식, 시험조건·대표값 혼동 | 추출값 원문 대조 필요; 수치 추출 성공만으로 정확성 보장 불가 |
| 제한된 탐색 범위 | 지정 제조사·카탈로그 및 최초 최대 5,000개 조합 중심 | 시장 전체·전체 조합 최적해 보장 불가, 열거 순서 영향 |
| 불완전한 데이터 | UNKNOWN 후보 유지, 개별 검사 결과 전체의 최종 상태 재집계 미흡, 소비전력 부분 합산 | 추천 상태·전력 순위 과대평가 가능; 데이터 완전성 확인 필요 |
| 단순화된 성능 모델 | 실제 레벨 제어 가능성 가정, 전원·열·임피던스·스퓨리어스 등 종합 검증 부재 | 회로 시뮬레이션·시제품 측정 추가 필요 |
| 송수신 계산 연계 | 선택 Rx 체인 NF의 링크 계산 자동 반영 없음, G/T와 SNR 계산 경로 분리 | 송수신 통합 성능 검토 시 입력값·모델 일관성 확인 필요 |
| 실제 구매·배열 설계 | 가격·재고·납기, 전체 안테나 배열 수량 및 우주환경 인증 검증 제외 | 최종 BOM·구매·양산 판단용 추가 검토 필요 |

활용 범위: **초기 부품 조사, 평가용 RF 체인 구성, 요구조건별 후보 비교**. 최종 회로 확정 단계에는 원문 사양 확인·상세 해석·실측 검증 필요.

작성 근거: [설계 API](backend/app/design/routes.py), [카탈로그 API](backend/app/catalog/routes.py), [Vue.js 화면](frontend/src/App.vue), [수집 파이프라인](scripts/pipeline.py), [후보 생성·정렬](backend/app/design/candidates.py), [호환성 검사](backend/app/design/compatibility.py), [계산 모듈](backend/app/design/). 저장소 구현 기준 정리.

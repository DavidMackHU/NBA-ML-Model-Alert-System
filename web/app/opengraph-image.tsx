import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "NBA +EV Alert System";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OgImage() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "#09090b",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "center",
          padding: "80px",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
            marginBottom: "32px",
          }}
        >
          <div
            style={{
              width: "14px",
              height: "14px",
              borderRadius: "50%",
              background: "#10b981",
            }}
          />
          <span
            style={{ color: "#a1a1aa", fontSize: "22px", letterSpacing: "0.08em" }}
          >
            NBA +EV
          </span>
        </div>
        <div
          style={{
            color: "#f4f4f5",
            fontSize: "56px",
            fontWeight: 700,
            lineHeight: 1.1,
            maxWidth: "900px",
          }}
        >
          NBA +EV Alert System
        </div>
        <div
          style={{
            color: "#71717a",
            fontSize: "26px",
            marginTop: "28px",
            maxWidth: "780px",
            lineHeight: 1.4,
          }}
        >
          Candidate edges · CLV tracking · honest backtest analysis
        </div>
      </div>
    ),
    { ...size },
  );
}

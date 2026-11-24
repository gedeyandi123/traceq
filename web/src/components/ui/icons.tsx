import type { SVGProps } from "react";

/** Shared props for inline SVG icons. Colours always inherit via `currentColor` (ADR 0011). */
export type IconProps = {
  className?: string;
  size?: number;
};

function Svg({
  size = 16,
  className,
  children,
  ...props
}: IconProps & Omit<SVGProps<SVGSVGElement>, "width" | "height" | "aria-hidden">) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      {...props}
    >
      {children}
    </svg>
  );
}

export function CheckCircleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6.25" />
      <path d="M5.5 8.2 7.2 9.9 10.7 6.4" />
    </Svg>
  );
}

export function AlertTriangleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 2.2 14.2 13.2H1.8L8 2.2Z" />
      <path d="M8 6.2v3.3" />
      <circle cx="8" cy="11.4" r="0.5" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function AlertCircleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6.25" />
      <path d="M8 5v3.5" />
      <circle cx="8" cy="11" r="0.5" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6.25" />
      <path d="M8 7.5V11" />
      <circle cx="8" cy="5.2" r="0.5" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 3.5 10.5 8 6 12.5" />
    </Svg>
  );
}

export function ExternalLinkIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9.5 2.5h4v4" />
      <path d="M13.5 2.5 7.5 8.5" />
      <path d="M12.5 9.5v3a1 1 0 0 1-1 1h-8a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1h3" />
    </Svg>
  );
}

export function FileTextIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 2.25h5.2L12.5 5.5v8.25a.75.75 0 0 1-.75.75H4.75a.75.75 0 0 1-.75-.75V3a.75.75 0 0 1 .75-.75Z" />
      <path d="M9 2.5v3.25h3.25" />
      <path d="M5.75 8.5h4.5" />
      <path d="M5.75 11h3" />
    </Svg>
  );
}

export function ShieldCheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 1.8 13.2 4v3.8c0 3.2-2.2 5.4-5.2 6.4-3-1-5.2-3.2-5.2-6.4V4L8 1.8Z" />
      <path d="M5.7 8.1 7.3 9.7 10.5 6.5" />
    </Svg>
  );
}

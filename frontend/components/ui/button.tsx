import * as React from "react";
import {Slot} from "@radix-ui/react-slot";
import {cva, type VariantProps} from "class-variance-authority";
import {cn} from "@/lib/utils";

const buttonVariants = cva("inline-flex items-center justify-center rounded-lg text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50", {
  variants: {variant: {default: "bg-cyan-400 text-slate-950 hover:bg-cyan-300", secondary: "bg-slate-800 text-slate-100 hover:bg-slate-700", ghost: "hover:bg-slate-800 text-slate-300"}, size: {default: "h-10 px-4", sm: "h-8 px-3 text-xs", icon: "h-9 w-9"}},
  defaultVariants: {variant: "default", size: "default"},
});

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {asChild?: boolean;}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({className, variant, size, asChild = false, ...props}, ref) => {
  const Comp: any = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({variant, size, className}))} ref={ref as any} {...props} />;
});
Button.displayName = "Button";

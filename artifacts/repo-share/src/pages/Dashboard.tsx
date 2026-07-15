import { useState } from "react";
import { useLocation } from "wouter";
import { formatDateTime } from "@/lib/utils/date";
import { cn } from "@/lib/utils";
import {
  useListShareLinks,
  useCreateShareLink,
  useUpdateShareLink,
  useDeleteShareLink,
  useListSubmissions,
  useGetRepoTree,
  ShareLink,
  getListShareLinksQueryKey,
  getGetRepoTreeQueryKey,
} from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { 
  Plus, 
  Copy, 
  Trash2, 
  ExternalLink, 
  Github, 
  Calendar,
  FileCode2,
  Clock,
  GitPullRequest,
  CheckCircle2,
  XCircle,
  Link as LinkIcon,
  Search,
  Activity,
  ChevronRight,
  ChevronsUpDown,
  MoreVertical,
  Edit2,
  FolderTree,
  Loader2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { ScrollArea } from "@/components/ui/scroll-area";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { format } from "date-fns";
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

const createShareSchema = z.object({
  repoOwner: z.string().min(1, "Repository owner is required"),
  repoName: z.string().min(1, "Repository name is required"),
  filePaths: z.array(z.string().min(1)).min(1, "Pick at least one file"),
  shareMode: z.enum(["single", "separate"]),
  baseBranch: z.string().optional(),
  title: z.string().min(1, "Title is required"),
  description: z.string().optional(),
  expiresAt: z.string().optional(),
});

type CreateShareValues = z.infer<typeof createShareSchema>;

export default function Dashboard() {
  const { data: shareLinks, isLoading, error } = useListShareLinks();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [selectedLinkForDrawer, setSelectedLinkForDrawer] = useState<ShareLink | null>(null);

  return (
    <div className="min-h-screen bg-muted/30">
      <div className="container max-w-6xl py-10 px-4 md:px-6">
        <header className="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-primary mb-2">
              <div className="bg-primary/10 p-2 rounded-lg">
                <GitPullRequest className="w-6 h-6" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-foreground">Repo Share</h1>
            </div>
            <p className="text-muted-foreground max-w-xl">
              Distribute isolated edit access to individual repository files. 
              Changes arrive as pull requests, keeping your codebase secure.
            </p>
          </div>
          <Button 
            onClick={() => setIsCreateOpen(true)} 
            className="gap-2 shrink-0 shadow-sm"
          >
            <Plus className="w-4 h-4" />
            New Share Link
          </Button>
        </header>

        <main>
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[1, 2, 3].map((i) => (
                <Card key={i} className="animate-pulse">
                  <CardHeader className="gap-2">
                    <Skeleton className="h-5 w-1/2" />
                    <Skeleton className="h-4 w-3/4" />
                  </CardHeader>
                  <CardContent>
                    <Skeleton className="h-24 w-full" />
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : error ? (
            <div className="text-center py-20 border rounded-xl bg-card">
              <XCircle className="w-10 h-10 text-destructive mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground mb-2">Failed to load shares</h3>
              <p className="text-muted-foreground">Please check your connection and try again.</p>
            </div>
          ) : shareLinks?.length === 0 ? (
            <div className="text-center py-24 border border-dashed rounded-xl bg-card flex flex-col items-center justify-center">
              <div className="bg-primary/5 p-4 rounded-full mb-6">
                <LinkIcon className="w-10 h-10 text-primary" />
              </div>
              <h3 className="text-xl font-medium text-foreground mb-2">No share links yet</h3>
              <p className="text-muted-foreground max-w-md mx-auto mb-8">
                Create a share link to hand out controlled edit access to a specific file in your repository.
              </p>
              <Button onClick={() => setIsCreateOpen(true)} className="gap-2">
                <Plus className="w-4 h-4" />
                Create your first link
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {shareLinks?.map((link) => (
                <ShareCard 
                  key={link.id} 
                  link={link} 
                  onOpenDetails={() => setSelectedLinkForDrawer(link)}
                />
              ))}
            </div>
          )}
        </main>
      </div>

      <CreateShareDialog open={isCreateOpen} onOpenChange={setIsCreateOpen} />
      <ShareDetailsDrawer 
        link={selectedLinkForDrawer} 
        onOpenChange={(open) => !open && setSelectedLinkForDrawer(null)} 
      />
    </div>
  );
}

function ShareCard({ link, onOpenDetails }: { link: ShareLink, onOpenDetails: () => void }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const updateShare = useUpdateShareLink();
  const deleteShare = useDeleteShareLink();
  
  const isExpired = link.expiresAt && new Date(link.expiresAt) < new Date();
  const shareUrl = `${window.location.origin}${import.meta.env.BASE_URL.replace(/\/$/, '')}/s/${link.slug}`;

  const copyUrl = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(shareUrl);
    toast({
      title: "Copied to clipboard",
      description: "Share link is ready to send.",
    });
  };

  const toggleActive = (checked: boolean) => {
    updateShare.mutate(
      { slug: link.slug, data: { isActive: checked } },
      {
        onSuccess: (data) => {
          queryClient.setQueryData(getListShareLinksQueryKey(), (old: ShareLink[] | undefined) => 
            old?.map(l => l.id === link.id ? { ...l, isActive: data.isActive } : l)
          );
          toast({
            title: checked ? "Link activated" : "Link deactivated",
            description: checked ? "The file can now be edited publicly." : "The public link will no longer accept submissions.",
          });
        }
      }
    );
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm("Are you sure you want to delete this share link? This will break any existing links.")) {
      deleteShare.mutate(
        { slug: link.slug },
        {
          onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: getListShareLinksQueryKey() });
            toast({
              title: "Share link deleted",
            });
          }
        }
      );
    }
  };

  return (
    <Card 
      className="group relative overflow-hidden flex flex-col transition-all duration-200 hover:shadow-md hover:border-primary/20 cursor-pointer"
      onClick={onOpenDetails}
    >
      <div className={`absolute top-0 left-0 w-1 h-full ${
        !link.isActive ? 'bg-muted' : isExpired ? 'bg-destructive/60' : 'bg-primary'
      }`} />
      
      <CardHeader className="pb-3 pt-5 px-5">
        <div className="flex justify-between items-start mb-1">
          <div className="flex items-center gap-2">
            {!link.isActive ? (
              <Badge variant="secondary" className="font-normal">Inactive</Badge>
            ) : isExpired ? (
              <Badge variant="destructive" className="font-normal bg-destructive/10 text-destructive hover:bg-destructive/20 border-0">Expired</Badge>
            ) : (
              <Badge variant="default" className="font-normal bg-primary/10 text-primary hover:bg-primary/20 border-0">Active</Badge>
            )}
            
            {link.submissionCount > 0 && (
              <Badge variant="outline" className="font-normal flex items-center gap-1 bg-accent">
                <GitPullRequest className="w-3 h-3" />
                {link.submissionCount}
              </Badge>
            )}
          </div>
          
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={e => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-8 w-8 -mt-2 -mr-2 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={copyUrl} className="gap-2">
                <Copy className="h-4 w-4" /> Copy public link
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => window.open(`/s/${link.slug}`, '_blank')} className="gap-2">
                <ExternalLink className="h-4 w-4" /> View public page
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleDelete} className="gap-2 text-destructive focus:text-destructive">
                <Trash2 className="h-4 w-4" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        
        <CardTitle className="text-lg leading-tight line-clamp-1 mt-1" title={link.title}>
          {link.title}
        </CardTitle>
        <CardDescription className="line-clamp-2 mt-1 min-h-[2.5rem]">
          {link.description || <span className="italic opacity-50">No description</span>}
        </CardDescription>
      </CardHeader>
      
      <CardContent className="px-5 py-3 flex-grow border-y bg-muted/10 border-border/50">
        <div className="space-y-2.5 text-sm">
          <div className="flex items-start gap-2.5 overflow-hidden">
            <Github className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
            <span className="truncate font-medium text-foreground/80" title={`${link.repoOwner}/${link.repoName}`}>
              {link.repoOwner}/{link.repoName}
            </span>
          </div>
          <div className="flex items-start gap-2.5 overflow-hidden">
            <FileCode2 className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
            <span
              className="truncate font-mono text-xs bg-muted/50 px-1 py-0.5 rounded"
              title={link.filePaths.join(", ")}
            >
              {link.filePaths.length === 1
                ? link.filePaths[0]
                : `${link.filePaths.length} files: ${link.filePaths.join(", ")}`}
            </span>
          </div>
        </div>
      </CardContent>
      
      <CardFooter className="px-5 py-3 flex justify-between items-center bg-card mt-auto">
        <div className="flex items-center gap-2">
          <Switch 
            checked={link.isActive} 
            onCheckedChange={toggleActive}
            onClick={e => e.stopPropagation()}
            aria-label="Toggle active status"
          />
          <span className="text-xs font-medium text-muted-foreground select-none">
            {link.isActive ? 'Accepting edits' : 'Paused'}
          </span>
        </div>
        
        <Tooltip>
          <TooltipTrigger asChild>
            <Button 
              variant="secondary" 
              size="sm" 
              className="h-8 gap-1.5"
              onClick={copyUrl}
            >
              <Copy className="h-3.5 w-3.5" />
              Copy URL
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top">Copy public share link</TooltipContent>
        </Tooltip>
      </CardFooter>
    </Card>
  );
}

const MAX_SHARE_FILES = 5;

function FilePicker({
  values,
  onChange,
  owner,
  repo,
  branch,
}: {
  values: string[];
  onChange: (values: string[]) => void;
  owner?: string;
  repo?: string;
  branch?: string;
}) {
  const [open, setOpen] = useState(false);
  const [manualPath, setManualPath] = useState("");
  const canBrowse = Boolean(owner && repo);
  const atLimit = values.length >= MAX_SHARE_FILES;

  const { data, isFetching, isError } = useGetRepoTree(
    { owner: owner || "", repo: repo || "", branch: branch || undefined },
    {
      query: {
        enabled: open && canBrowse,
        queryKey: getGetRepoTreeQueryKey({ owner: owner || "", repo: repo || "", branch: branch || undefined }),
        staleTime: 60_000,
      },
    }
  );

  const toggle = (path: string) => {
    if (values.includes(path)) {
      onChange(values.filter((v) => v !== path));
    } else if (!atLimit) {
      onChange([...values, path]);
    }
  };

  const addManualPath = () => {
    const path = manualPath.trim();
    if (!path || values.includes(path) || atLimit) return;
    onChange([...values, path]);
    setManualPath("");
  };

  return (
    <div className="space-y-2">
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {values.map((path) => (
            <Badge key={path} variant="secondary" className="font-mono text-xs gap-1.5 pr-1">
              {path}
              <button
                type="button"
                onClick={() => toggle(path)}
                className="hover:bg-muted rounded-sm p-0.5"
                aria-label={`Remove ${path}`}
              >
                <XCircle className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={atLimit}
            className="w-full justify-between font-normal text-sm"
          >
            <span className={cn("truncate", values.length === 0 && "text-muted-foreground")}>
              {atLimit
                ? `Maximum of ${MAX_SHARE_FILES} files selected`
                : canBrowse
                ? `Add a file${values.length > 0 ? ` (${values.length}/${MAX_SHARE_FILES})` : ""}...`
                : "Enter repo owner and name first"}
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[420px] p-0" align="start">
          <Command shouldFilter={true}>
            <CommandInput placeholder="Search files..." />
            <CommandList>
              {!canBrowse && (
                <div className="py-6 text-center text-sm text-muted-foreground">
                  Enter the repo owner and name to browse its files.
                </div>
              )}
              {canBrowse && isFetching && (
                <div className="py-6 flex items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Reading repository...
                </div>
              )}
              {canBrowse && isError && (
                <div className="py-6 text-center text-sm text-muted-foreground px-4">
                  Could not read this repository. Type the file path manually below.
                </div>
              )}
              {canBrowse && !isFetching && !isError && (
                <>
                  <CommandEmpty>No matching files. You can still type a custom path below.</CommandEmpty>
                  <CommandGroup heading={data ? `${data.files.length} files on ${branch || data.defaultBranch}` : undefined}>
                    {data?.files.map((path) => {
                      const selected = values.includes(path);
                      return (
                        <CommandItem
                          key={path}
                          value={path}
                          onSelect={() => toggle(path)}
                          className="font-mono text-xs"
                        >
                          <div
                            className={cn(
                              "mr-2 h-3.5 w-3.5 shrink-0 rounded-sm border flex items-center justify-center",
                              selected ? "bg-primary border-primary" : "border-muted-foreground/40"
                            )}
                          >
                            {selected && <CheckCircle2 className="h-3 w-3 text-primary-foreground" />}
                          </div>
                          <FileCode2 className="h-3.5 w-3.5 mr-2 shrink-0 text-muted-foreground" />
                          <span className="truncate">{path}</span>
                        </CommandItem>
                      );
                    })}
                  </CommandGroup>
                </>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      <div className="flex gap-2">
        <Input
          placeholder="Or type a file path manually..."
          value={manualPath}
          onChange={(e) => setManualPath(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addManualPath();
            }
          }}
          disabled={atLimit}
          className="font-mono text-xs"
        />
        <Button type="button" variant="outline" onClick={addManualPath} disabled={atLimit || !manualPath.trim()}>
          Add
        </Button>
      </div>
    </div>
  );
}

function CreateShareDialog({ open, onOpenChange }: { open: boolean, onOpenChange: (open: boolean) => void }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const createShare = useCreateShareLink();
  
  const form = useForm<CreateShareValues>({
    resolver: zodResolver(createShareSchema),
    defaultValues: {
      repoOwner: "",
      repoName: "",
      filePaths: [],
      shareMode: "single",
      baseBranch: "main",
      title: "",
      description: "",
      expiresAt: "",
    },
  });

  const onSubmit = async (data: CreateShareValues) => {
    const expiresAt = data.expiresAt ? new Date(data.expiresAt).toISOString() : undefined;
    const baseBranch = data.baseBranch || undefined;

    try {
      let urls: string[];

      if (data.shareMode === "single" || data.filePaths.length === 1) {
        const newLink = await createShare.mutateAsync({
          data: {
            repoOwner: data.repoOwner,
            repoName: data.repoName,
            filePaths: data.filePaths,
            baseBranch,
            title: data.title,
            description: data.description,
            expiresAt,
          },
        });
        urls = [`${window.location.origin}${import.meta.env.BASE_URL.replace(/\/$/, '')}/s/${newLink.slug}`];
      } else {
        const links = await Promise.all(
          data.filePaths.map((filePath, i) =>
            createShare.mutateAsync({
              data: {
                repoOwner: data.repoOwner,
                repoName: data.repoName,
                filePaths: [filePath],
                baseBranch,
                title: data.filePaths.length > 1 ? `${data.title} — ${filePath}` : data.title,
                description: data.description,
                expiresAt,
              },
            })
          )
        );
        urls = links.map(
          (link) => `${window.location.origin}${import.meta.env.BASE_URL.replace(/\/$/, '')}/s/${link.slug}`
        );
      }

      queryClient.invalidateQueries({ queryKey: getListShareLinksQueryKey() });
      onOpenChange(false);
      form.reset();

      navigator.clipboard.writeText(urls.join("\n"));

      toast({
        title: urls.length > 1 ? `${urls.length} share links created` : "Share link created",
        description: urls.length > 1
          ? "All public URLs have been copied to your clipboard."
          : "The public URL has been copied to your clipboard.",
      });
    } catch (error: any) {
      toast({
        title: "Failed to create share link",
        description: error?.data?.error || "An unexpected error occurred.",
        variant: "destructive",
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-2">
          <DialogTitle className="text-xl">Create Share Link</DialogTitle>
          <DialogDescription>
            Hand out a focused, isolated editing environment for a specific file.
          </DialogDescription>
        </DialogHeader>
        
        <ScrollArea className="px-6 max-h-[60vh]">
          <Form {...form}>
            <form id="create-share-form" onSubmit={form.handleSubmit(onSubmit)} className="space-y-4 py-4">
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Title</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. Fix copy on pricing page" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              
              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description (Optional)</FormLabel>
                    <FormControl>
                      <Textarea 
                        placeholder="Context for whoever is editing this file..." 
                        className="resize-none h-20"
                        {...field} 
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              
              <div className="grid grid-cols-2 gap-4 p-4 bg-muted/30 rounded-lg border">
                <FormField
                  control={form.control}
                  name="repoOwner"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Repo Owner</FormLabel>
                      <FormControl>
                        <Input placeholder="vercel" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <FormField
                  control={form.control}
                  name="repoName"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Repo Name</FormLabel>
                      <FormControl>
                        <Input placeholder="next.js" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <div className="col-span-2">
                  <FormField
                    control={form.control}
                    name="filePaths"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Files (up to {MAX_SHARE_FILES})</FormLabel>
                        <FormControl>
                          <FilePicker
                            values={field.value}
                            onChange={field.onChange}
                            owner={form.watch("repoOwner")}
                            repo={form.watch("repoName")}
                            branch={form.watch("baseBranch")}
                          />
                        </FormControl>
                        <FormDescription>Browse the repo, or type paths relative to its root</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </div>

              {form.watch("filePaths").length > 1 && (
                <FormField
                  control={form.control}
                  name="shareMode"
                  render={({ field }) => (
                    <FormItem className="space-y-2 p-4 bg-muted/30 rounded-lg border">
                      <FormLabel>How should these files be shared?</FormLabel>
                      <FormControl>
                        <RadioGroup
                          value={field.value}
                          onValueChange={field.onChange}
                          className="space-y-2"
                        >
                          <label className="flex items-start gap-2.5 cursor-pointer">
                            <RadioGroupItem value="single" id="mode-single" className="mt-0.5" />
                            <div>
                              <div className="text-sm font-medium leading-none">One link for all files</div>
                              <div className="text-xs text-muted-foreground mt-1">
                                A single URL lets an editor update all {form.watch("filePaths").length} files together as one pull request.
                              </div>
                            </div>
                          </label>
                          <label className="flex items-start gap-2.5 cursor-pointer">
                            <RadioGroupItem value="separate" id="mode-separate" className="mt-0.5" />
                            <div>
                              <div className="text-sm font-medium leading-none">One link per file</div>
                              <div className="text-xs text-muted-foreground mt-1">
                                Creates {form.watch("filePaths").length} separate URLs, each scoped to a single file.
                              </div>
                            </div>
                          </label>
                        </RadioGroup>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
              
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="baseBranch"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Base Branch</FormLabel>
                      <FormControl>
                        <Input placeholder="main" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <FormField
                  control={form.control}
                  name="expiresAt"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Expires At (Optional)</FormLabel>
                      <FormControl>
                        <Input type="datetime-local" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </form>
          </Form>
        </ScrollArea>
        
        <DialogFooter className="px-6 py-4 border-t bg-muted/10">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button 
            type="submit" 
            form="create-share-form"
            disabled={createShare.isPending}
            className="gap-2"
          >
            {createShare.isPending && <Activity className="w-4 h-4 animate-spin" />}
            Create & Copy URL
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ShareDetailsDrawer({ link, onOpenChange }: { link: ShareLink | null, onOpenChange: (open: boolean) => void }) {
  const { data: submissions, isLoading } = useListSubmissions(link?.slug || "", {
    query: {
      enabled: !!link?.slug,
      queryKey: link ? ["submissions", link.slug] : ["submissions"],
    }
  });

  return (
    <Drawer open={!!link} onOpenChange={onOpenChange}>
      <DrawerContent className="max-h-[85vh]">
        {link && (
          <div className="mx-auto w-full max-w-3xl flex flex-col h-full overflow-hidden">
            <DrawerHeader className="text-left px-6 py-4 border-b">
              <div className="flex items-center gap-3 mb-1">
                <div className={`w-2.5 h-2.5 rounded-full ${link.isActive ? 'bg-primary' : 'bg-muted-foreground'}`} />
                <DrawerTitle className="text-xl font-bold">{link.title}</DrawerTitle>
              </div>
              <DrawerDescription className="flex items-center gap-4 text-sm mt-1">
                <span className="flex items-center gap-1.5">
                  <Github className="w-3.5 h-3.5" />
                  {link.repoOwner}/{link.repoName}
                </span>
                <span className="flex items-center gap-1.5 font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
                  <FileCode2 className="w-3.5 h-3.5" />
                  {link.filePaths.length === 1
                    ? link.filePaths[0]
                    : `${link.filePaths.length} files`}
                </span>
              </DrawerDescription>
            </DrawerHeader>
            
            <ScrollArea className="flex-1 px-6 py-6 overflow-y-auto">
              <div className="space-y-8">
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4">Pull Request History</h3>
                  
                  {isLoading ? (
                    <div className="space-y-3">
                      {[1, 2].map(i => (
                        <div key={i} className="flex gap-4 p-4 border rounded-lg animate-pulse">
                          <div className="w-8 h-8 rounded-full bg-muted" />
                          <div className="space-y-2 flex-1">
                            <div className="h-4 w-1/4 bg-muted rounded" />
                            <div className="h-3 w-1/2 bg-muted rounded" />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : submissions?.length === 0 ? (
                    <div className="text-center py-12 border border-dashed rounded-lg bg-muted/10">
                      <GitPullRequest className="w-8 h-8 text-muted-foreground/50 mx-auto mb-3" />
                      <p className="text-sm font-medium text-foreground">No submissions yet</p>
                      <p className="text-xs text-muted-foreground mt-1">When someone edits the file, their changes will appear here.</p>
                    </div>
                  ) : (
                    <div className="relative border-l-2 border-muted ml-4 space-y-6 pb-4">
                      {submissions?.map((sub) => (
                        <div key={sub.id} className="relative pl-6">
                          <div className="absolute w-4 h-4 bg-background border-2 border-primary rounded-full -left-[9px] top-1" />
                          
                          <Card className="shadow-sm border-muted-foreground/10 hover:border-primary/30 transition-colors">
                            <CardContent className="p-4">
                              <div className="flex justify-between items-start mb-3">
                                <div>
                                  <div className="flex items-center gap-2 mb-1">
                                    <span className="font-medium text-sm">
                                      {sub.submitterName || "Anonymous User"}
                                    </span>
                                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                                      <Clock className="w-3 h-3" />
                                      {formatDateTime(sub.createdAt)}
                                    </span>
                                  </div>
                                  {sub.note && (
                                    <p className="text-sm text-muted-foreground bg-muted/30 p-2 rounded border border-border/50 inline-block mt-1">
                                      "{sub.note}"
                                    </p>
                                  )}
                                </div>
                                <Button size="sm" variant="outline" className="gap-2 shrink-0 h-8" asChild>
                                  <a href={sub.prUrl} target="_blank" rel="noreferrer">
                                    <Github className="w-3.5 h-3.5" />
                                    PR #{sub.prNumber}
                                  </a>
                                </Button>
                              </div>
                              <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground bg-muted/30 px-2 py-1 rounded inline-flex">
                                <GitPullRequest className="w-3 h-3" />
                                {sub.branchName}
                              </div>
                            </CardContent>
                          </Card>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </ScrollArea>
          </div>
        )}
      </DrawerContent>
    </Drawer>
  );
}

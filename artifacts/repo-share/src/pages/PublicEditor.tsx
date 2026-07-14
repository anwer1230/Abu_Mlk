import { useState } from "react";
import { useRoute, useLocation } from "wouter";
import { 
  useGetShareLink, 
  useCreateSubmission,
  getGetShareLinkQueryKey
} from "@workspace/api-client-react";
import type { GetShareLinkQueryError } from "@workspace/api-client-react";
import { 
  FileCode2, 
  Github, 
  GitPullRequest, 
  AlertCircle, 
  Lock, 
  Clock, 
  Send,
  User,
  MessageSquare,
  CheckCircle2,
  ExternalLink,
  ChevronLeft
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { Link } from "wouter";

export default function PublicEditor() {
  const [, params] = useRoute("/s/:slug");
  const slug = params?.slug || "";
  
  const { data: share, isLoading, error } = useGetShareLink(slug, {
    query: { enabled: !!slug, queryKey: getGetShareLinkQueryKey(slug) }
  });
  
  const createSubmission = useCreateSubmission();
  const { toast } = useToast();
  
  const [content, setContent] = useState("");
  const [isEdited, setIsEdited] = useState(false);
  const [submitterName, setSubmitterName] = useState("");
  const [note, setNote] = useState("");
  const [submittedPrUrl, setSubmittedPrUrl] = useState<string | null>(null);

  // Initialize content once loaded
  if (share?.fileContent !== undefined && !isEdited && content === "") {
    setContent(share.fileContent);
  }

  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setContent(e.target.value);
    if (!isEdited) setIsEdited(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!content.trim()) {
      toast({
        title: "Empty content",
        description: "You cannot submit an empty file.",
        variant: "destructive"
      });
      return;
    }

    createSubmission.mutate(
      { 
        slug, 
        data: { 
          content,
          submitterName: submitterName || undefined,
          note: note || undefined
        } 
      },
      {
        onSuccess: (submission) => {
          setSubmittedPrUrl(submission.prUrl);
          toast({
            title: "Changes submitted successfully",
            description: "A pull request has been opened for review.",
          });
        },
        onError: (err) => {
          toast({
            title: "Failed to submit changes",
            description: err.data?.error || "An error occurred while creating the pull request.",
            variant: "destructive"
          });
        }
      }
    );
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center p-4">
        <Card className="w-full max-w-4xl shadow-lg border-muted">
          <CardHeader className="gap-2 border-b bg-muted/10 pb-6">
            <Skeleton className="h-8 w-1/3" />
            <Skeleton className="h-4 w-1/2" />
          </CardHeader>
          <CardContent className="p-0">
            <Skeleton className="h-[60vh] w-full rounded-none" />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error || !share) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center p-4">
        <Card className="w-full max-w-md shadow-md border-muted text-center py-10">
          <AlertCircle className="w-12 h-12 text-destructive mx-auto mb-4 opacity-80" />
          <CardTitle className="text-xl mb-2">Link Not Found</CardTitle>
          <CardDescription className="text-base px-6">
            This share link doesn't exist, has been removed, or the URL is incorrect.
          </CardDescription>
        </Card>
      </div>
    );
  }

  const isExpired = share.expiresAt && new Date(share.expiresAt) < new Date();
  
  if (!share.isActive || isExpired) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center p-4">
        <Card className="w-full max-w-md shadow-md border-muted text-center py-10">
          {isExpired ? (
            <Clock className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-80" />
          ) : (
            <Lock className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-80" />
          )}
          <CardTitle className="text-xl mb-2">
            {isExpired ? "Link Expired" : "Link Inactive"}
          </CardTitle>
          <CardDescription className="text-base px-6">
            {isExpired 
              ? "This share link has expired and is no longer accepting edits." 
              : "This share link has been temporarily paused by the repository owner."}
          </CardDescription>
        </Card>
      </div>
    );
  }

  if (submittedPrUrl) {
    return (
      <div className="min-h-screen bg-muted/30 flex flex-col items-center justify-center p-4">
        <div className="w-full max-w-xl">
          <Card className="shadow-lg border-primary/20 overflow-hidden relative">
            <div className="absolute top-0 left-0 w-full h-2 bg-primary" />
            <CardHeader className="text-center pt-10 pb-6">
              <div className="mx-auto w-16 h-16 bg-primary/10 flex items-center justify-center rounded-full mb-6 text-primary">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <CardTitle className="text-2xl mb-2">Changes Submitted</CardTitle>
              <CardDescription className="text-base text-foreground/80">
                Your edits have been successfully forwarded to the repository owner as a pull request.
              </CardDescription>
            </CardHeader>
            <CardContent className="bg-muted/10 p-8 border-y">
              <div className="flex flex-col items-center text-center space-y-4">
                <p className="text-sm text-muted-foreground mb-2">
                  Nothing was pushed directly to the base branch. The maintainers will review your submission before it gets merged.
                </p>
                <Button asChild size="lg" className="gap-2 w-full sm:w-auto font-medium">
                  <a href={submittedPrUrl} target="_blank" rel="noreferrer">
                    <Github className="w-5 h-5" />
                    View Pull Request on GitHub
                    <ExternalLink className="w-4 h-4 ml-1 opacity-50" />
                  </a>
                </Button>
              </div>
            </CardContent>
            <CardFooter className="justify-center py-6">
              <Button variant="ghost" onClick={() => setSubmittedPrUrl(null)} className="text-muted-foreground">
                Submit another change
              </Button>
            </CardFooter>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b bg-card sticky top-0 z-10 shadow-sm shadow-black/5">
        <div className="container max-w-6xl mx-auto px-4 py-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <div className="bg-primary text-primary-foreground p-1.5 rounded flex items-center justify-center">
                  <FileCode2 className="w-4 h-4" />
                </div>
                <h1 className="text-xl font-bold tracking-tight text-foreground leading-none">
                  {share.title}
                </h1>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-2 text-sm text-muted-foreground">
                <span className="flex items-center gap-1.5 font-medium text-foreground/80">
                  <Github className="w-4 h-4" />
                  {share.repoOwner}/{share.repoName}
                </span>
                <span className="flex items-center gap-1.5 font-mono text-xs bg-muted px-2 py-0.5 rounded text-foreground/70">
                  {share.filePath}
                </span>
                {share.baseBranch && (
                  <span className="flex items-center gap-1.5 text-xs">
                    <GitPullRequest className="w-3.5 h-3.5" />
                    base: {share.baseBranch}
                  </span>
                )}
              </div>
            </div>
            
            {share.description && (
              <div className="md:max-w-xs text-sm bg-muted/40 p-3 rounded-lg border border-border/50 text-foreground/80">
                {share.description}
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 container max-w-6xl mx-auto px-4 py-6 flex flex-col lg:flex-row gap-6">
        <div className="flex-1 flex flex-col min-h-[500px] border rounded-xl overflow-hidden shadow-sm bg-card">
          <div className="bg-muted px-4 py-2 border-b flex items-center justify-between font-mono text-xs text-muted-foreground">
            <span>{share.filePath}</span>
            <Badge variant="outline" className="font-sans text-[10px] uppercase tracking-wider bg-background">Editing</Badge>
          </div>
          <Textarea 
            value={content}
            onChange={handleContentChange}
            className="flex-1 rounded-none border-0 focus-visible:ring-0 resize-none font-mono text-sm p-4 bg-transparent leading-relaxed"
            placeholder="File content..."
            spellCheck={false}
          />
        </div>

        <aside className="w-full lg:w-80 shrink-0">
          <Card className="sticky top-28 shadow-md border-primary/10">
            <CardHeader className="pb-4 bg-muted/10 border-b">
              <CardTitle className="text-lg flex items-center gap-2">
                <Send className="w-4 h-4 text-primary" />
                Submit Edit
              </CardTitle>
              <CardDescription>
                Propose changes to this file. A pull request will be opened for review.
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-6">
              <form id="submission-form" onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="submitterName" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                    <User className="w-3.5 h-3.5" />
                    Your Name (Optional)
                  </Label>
                  <Input 
                    id="submitterName" 
                    placeholder="Jane Doe" 
                    value={submitterName}
                    onChange={e => setSubmitterName(e.target.value)}
                    className="bg-muted/30 focus:bg-background transition-colors"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="note" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                    <MessageSquare className="w-3.5 h-3.5" />
                    Commit Note (Optional)
                  </Label>
                  <Textarea 
                    id="note" 
                    placeholder="Briefly describe what you changed..." 
                    value={note}
                    onChange={e => setNote(e.target.value)}
                    className="resize-none h-24 bg-muted/30 focus:bg-background transition-colors"
                  />
                </div>
              </form>
            </CardContent>
            <CardFooter className="pt-2 pb-6 px-6 bg-muted/5 border-t">
              <Button 
                type="submit" 
                form="submission-form" 
                className="w-full font-medium"
                size="lg"
                disabled={createSubmission.isPending}
              >
                {createSubmission.isPending ? (
                  <span className="flex items-center gap-2">
                    <div className="w-4 h-4 rounded-full border-2 border-primary-foreground border-t-transparent animate-spin" />
                    Submitting...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <GitPullRequest className="w-4 h-4" />
                    Open Pull Request
                  </span>
                )}
              </Button>
            </CardFooter>
          </Card>
        </aside>
      </main>
    </div>
  );
}
